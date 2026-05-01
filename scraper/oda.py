"""Oda.com price scraper — fallback when Kassal data is missing.

Uses curl_cffi to spoof a Chrome TLS fingerprint, bypassing Cloudflare
bot detection. Hits Oda's internal REST API (v1), not the HTML.

Discovery method: Chrome DevTools → Network tab → filter 'api/v1/products'.
"""
from __future__ import annotations

import asyncio
from datetime import date

import structlog
from curl_cffi.requests import AsyncSession
from tenacity import retry, stop_after_attempt, wait_exponential

from scraper.config import settings

log = structlog.get_logger(__name__)

ODA_API = "https://oda.com/api/v1/products/"

# Impersonate Chrome 120 — spoofs JA3 fingerprint + HTTP/2 ALPN
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
async def _get_oda(session: AsyncSession, ean: str) -> dict | None:
    resp = await session.get(
        ODA_API,
        params={"search": ean},
        headers=_HEADERS,
        timeout=settings.request_timeout,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    data = resp.json()
    items = data.get("results", [])
    return items[0] if items else None


async def fetch_prices_batch(eans: list[str]) -> list[dict]:
    today = date.today()
    results: list[dict] = []
    sem = asyncio.Semaphore(settings.max_concurrency)

    async def fetch_one(session: AsyncSession, ean: str) -> None:
        async with sem:
            try:
                item = await _get_oda(session, ean)
                if not item:
                    return
                gross = item.get("gross_price")
                if gross is None:
                    return
                results.append(
                    {
                        "ean": ean,
                        "price_date": today,
                        "price": float(gross),
                        "is_promo": bool(item.get("promotion")),
                        "promo_price": float(item["promotion"]["price"]) if item.get("promotion") else None,
                        "source": "oda_api",
                    }
                )
            except Exception:
                log.exception("oda_fetch_failed", ean=ean)

    async with AsyncSession(impersonate=_IMPERSONATE) as session:
        await asyncio.gather(*[fetch_one(session, ean) for ean in eans])

    log.info("oda_batch_done", fetched=len(results), requested=len(eans))
    return results
