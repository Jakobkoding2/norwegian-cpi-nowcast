"""Oda.com price scraper — fallback when Kassal data is missing.

Uses curl_cffi to spoof a Chrome TLS fingerprint, bypassing Cloudflare
bot detection. Hits Oda's public search API (not the HTML).

Endpoint confirmed working: GET https://oda.com/api/v1/search/?q={name}
Note: Oda does not expose EANs in search results, so we match by name and
map the price back to our db EAN. The price is for a similar product in the
same category — close enough for an index fallback.
"""
from __future__ import annotations

import asyncio
from datetime import date

import structlog
from curl_cffi.requests import AsyncSession
from tenacity import retry, stop_after_attempt, wait_exponential

from scraper.config import settings

log = structlog.get_logger(__name__)

ODA_SEARCH_API = "https://oda.com/api/v1/search/"
_IMPERSONATE = "chrome120"

_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "nb-NO,nb;q=0.9",
    "Referer": "https://oda.com/no/",
}


@retry(
    stop=stop_after_attempt(settings.retry_attempts),
    wait=wait_exponential(multiplier=settings.retry_wait_seconds, min=2, max=30),
    reraise=True,
)
async def _search_oda(session: AsyncSession, name: str) -> list[dict]:
    resp = await session.get(
        ODA_SEARCH_API,
        params={"q": name, "page_size": 5},
        headers=_HEADERS,
        timeout=settings.request_timeout,
    )
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    return resp.json().get("products", [])


async def fetch_prices_batch(products: list[dict]) -> list[dict]:
    """Name-based search fallback. Returns price rows keyed by our db EAN.

    Accepts the same {ean, name} dict list as the Kassal scraper.
    """
    today = date.today()
    results: list[dict] = []
    sem = asyncio.Semaphore(settings.max_concurrency)

    async def fetch_one(session: AsyncSession, product: dict) -> None:
        db_ean: str = product["ean"]
        name: str = product["name"]
        base_price: float | None = product.get("base_price_p0")
        async with sem:
            try:
                hits = await _search_oda(session, name)
                hit = next((p for p in hits if p.get("gross_price") is not None), None)
                if hit is None:
                    return
                price = float(hit["gross_price"])
                # Sanity check: Oda name-matches can land on a larger/premium variant.
                # If price is more than 1.6× the January base, it's almost certainly
                # a wrong-size match — skip it rather than pollute the index.
                if base_price and price > base_price * 1.6:
                    log.warning(
                        "oda_price_sanity_fail",
                        name=name,
                        price=price,
                        base=base_price,
                        ratio=round(price / base_price, 2),
                    )
                    return
                discount = hit.get("discount") or hit.get("promotion")
                results.append(
                    {
                        "ean": db_ean,
                        "price_date": today,
                        "price": price,
                        "is_promo": bool(discount),
                        "promo_price": float(discount["price"]) if discount and "price" in discount else None,
                        "source": "oda_api",
                    }
                )
            except Exception:
                log.exception("oda_fetch_failed", name=name)

    async with AsyncSession(impersonate=_IMPERSONATE) as session:
        await asyncio.gather(*[fetch_one(session, p) for p in products])

    log.info("oda_batch_done", fetched=len(results), requested=len(products))
    return results
