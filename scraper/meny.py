"""Meny / NorgesGruppen price scraper — fallback source.

Meny's frontend queries the NGData Elasticsearch REST API.
Discovery: Chrome DevTools → Network → filter 'ngdata.no'.
Endpoint: https://platform-rest-prod.ngdata.no/api/products/10800/<store_id>/search
"""
from __future__ import annotations

import asyncio
from datetime import date

import structlog
from curl_cffi.requests import AsyncSession
from tenacity import retry, stop_after_attempt, wait_exponential

from scraper.config import settings

log = structlog.get_logger(__name__)

# Default store ID — Meny Byporten Oslo; representative urban pricing
_DEFAULT_STORE_ID = "7080001150886"
MENY_API = f"https://platform-rest-prod.ngdata.no/api/products/10800/{_DEFAULT_STORE_ID}/search"
_IMPERSONATE = "chrome120"

_HEADERS = {
    "Accept": "application/json",
    "Origin": "https://meny.no",
    "Referer": "https://meny.no/",
}


@retry(
    stop=stop_after_attempt(settings.retry_attempts),
    wait=wait_exponential(multiplier=settings.retry_wait_seconds, min=2, max=30),
    reraise=True,
)
async def _post_search(session: AsyncSession, ean: str) -> list[dict]:
    payload = {
        "query": ean,
        "size": 5,
        "from": 0,
    }
    resp = await session.post(
        MENY_API,
        json=payload,
        headers=_HEADERS,
        timeout=settings.request_timeout,
    )
    resp.raise_for_status()
    return resp.json().get("hits", {}).get("hits", [])


async def fetch_prices_batch(eans: list[str]) -> list[dict]:
    today = date.today()
    results: list[dict] = []
    sem = asyncio.Semaphore(settings.max_concurrency)

    async def fetch_one(session: AsyncSession, ean: str) -> None:
        async with sem:
            try:
                hits = await _post_search(session, ean)
                if not hits:
                    return
                src = hits[0].get("_source", {})
                price_info = src.get("priceV2", src.get("price", {}))
                raw_price = price_info.get("current") or price_info.get("price")
                if raw_price is None:
                    return
                promo = price_info.get("promotion", {})
                results.append(
                    {
                        "ean": ean,
                        "price_date": today,
                        "price": float(raw_price),
                        "is_promo": bool(promo),
                        "promo_price": float(promo["price"]) if promo and "price" in promo else None,
                        "source": "meny_api",
                    }
                )
            except Exception:
                log.exception("meny_fetch_failed", ean=ean)

    async with AsyncSession(impersonate=_IMPERSONATE) as session:
        await asyncio.gather(*[fetch_one(session, ean) for ean in eans])

    log.info("meny_batch_done", fetched=len(results), requested=len(eans))
    return results
