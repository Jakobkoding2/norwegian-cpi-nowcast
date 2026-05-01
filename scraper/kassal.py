"""Kassal.app API client — primary data source.

Kassal's search is name-based. Strategy:
- Search each product by name (from the products table).
- Take the first result whose EAN matches our DB record, or the best name match.
- Update the DB EAN if Kassal returns a different (real) one.
"""
from __future__ import annotations

import asyncio
from datetime import date

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from scraper.config import settings

log = structlog.get_logger(__name__)

BASE = settings.kassal_base_url
HEADERS = {
    "Authorization": f"Bearer {settings.kassal_api_key}",
    "Accept": "application/json",
}


@retry(
    stop=stop_after_attempt(settings.retry_attempts),
    wait=wait_exponential(multiplier=settings.retry_wait_seconds, min=2, max=30),
    reraise=True,
)
async def _search(client: httpx.AsyncClient, query: str) -> list[dict]:
    resp = await client.get(
        f"{BASE}/products",
        params={"search": query, "size": 5},
        headers=HEADERS,
        timeout=settings.request_timeout,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


async def fetch_prices_batch(products: list[dict]) -> list[dict]:
    """Fetch prices for a list of {ean, name} dicts via name search.

    Returns price rows keyed by the canonical EAN from our DB.
    Also returns a list of (old_ean, real_ean, base_price) corrections.
    """
    today = date.today()
    results: list[dict] = []
    ean_corrections: list[tuple[str, str, float]] = []
    sem = asyncio.Semaphore(settings.max_concurrency)

    async def fetch_one(client: httpx.AsyncClient, product: dict) -> None:
        db_ean: str = product["ean"]
        name: str = product["name"]
        async with sem:
            await asyncio.sleep(1.5)  # 2 slots / (1.5s sleep + ~1s request) ≈ 40 req/min, under 60/min limit
            try:
                hits = await _search(client, name)
                if not hits:
                    log.warning("kassal_no_results", name=name)
                    return

                # Prefer a hit whose EAN matches our DB record
                matched = next((h for h in hits if h["ean"] == db_ean), None)
                # Otherwise take the first hit with a current_price
                if matched is None:
                    matched = next((h for h in hits if h.get("current_price") is not None), None)

                if matched is None or matched.get("current_price") is None:
                    return

                real_ean: str | None = matched.get("ean")
                if not real_ean:
                    return
                price = float(matched["current_price"])

                # Track EAN correction so caller can update the DB
                if real_ean != db_ean:
                    ean_corrections.append((db_ean, real_ean, price))
                    use_ean = real_ean
                else:
                    use_ean = db_ean

                results.append(
                    {
                        "ean": use_ean,
                        "db_ean": db_ean,
                        "price_date": today,
                        "price": price,
                        "is_promo": matched.get("is_promoted", False),
                        "promo_price": None,
                        "source": "kassal",
                    }
                )
            except Exception:
                log.exception("kassal_fetch_failed", name=name)

    async with httpx.AsyncClient() as client:
        await asyncio.gather(*[fetch_one(client, p) for p in products])

    log.info(
        "kassal_batch_done",
        fetched=len(results),
        requested=len(products),
        ean_corrections=len(ean_corrections),
    )
    return results, ean_corrections  # type: ignore[return-value]
