"""Kassal.app API client — primary data source.

Docs: https://kassal.app/api (requires API key)
Rate limit: ~60 req/min on free tier.
"""
from __future__ import annotations

import asyncio
from datetime import date

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from scraper.config import settings

log = structlog.get_logger(__name__)

HEADERS = {
    "Authorization": f"Bearer {settings.kassal_api_key}",
    "Accept": "application/json",
}


@retry(
    stop=stop_after_attempt(settings.retry_attempts),
    wait=wait_exponential(multiplier=settings.retry_wait_seconds, min=2, max=30),
    reraise=True,
)
async def _get(client: httpx.AsyncClient, url: str, **params) -> dict:
    resp = await client.get(url, params=params, headers=HEADERS, timeout=settings.request_timeout)
    resp.raise_for_status()
    return resp.json()


async def fetch_prices_batch(eans: list[str]) -> list[dict]:
    """Fetch current prices for a list of EANs via Kassal product search.

    Returns a flat list of price dicts ready for DB insert.
    """
    today = date.today()
    results: list[dict] = []
    sem = asyncio.Semaphore(settings.max_concurrency)

    async def fetch_one(client: httpx.AsyncClient, ean: str) -> None:
        async with sem:
            try:
                data = await _get(
                    client,
                    f"{settings.kassal_base_url}/products",
                    search=ean,
                    size=5,
                )
                for product in data.get("data", []):
                    current = product.get("current_price")
                    if current is None:
                        continue
                    promo = product.get("current_unit_price")
                    results.append(
                        {
                            "ean": ean,
                            "price_date": today,
                            "price": float(current),
                            "is_promo": product.get("is_promoted", False),
                            "promo_price": float(promo) if promo else None,
                            "source": "kassal",
                        }
                    )
            except Exception:
                log.exception("kassal_fetch_failed", ean=ean)

    async with httpx.AsyncClient(http2=True) as client:
        await asyncio.gather(*[fetch_one(client, ean) for ean in eans])

    log.info("kassal_batch_done", fetched=len(results), requested=len(eans))
    return results
