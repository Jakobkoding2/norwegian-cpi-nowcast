"""Entry point for the daily price ingestion pipeline.

Run at 02:00 daily via GitHub Actions or Docker cron.
Strategy:
  1. Fetch all active products (ean + name) from the DB.
  2. Search Kassal by name (primary — official API).
  3. For any product that returned no price, fall back to Oda then Meny.
  4. Apply any EAN corrections discovered during the Kassal search.
  5. Write everything to raw_prices (idempotent).
"""
from __future__ import annotations

import asyncio
import sys

import structlog

from scraper import kassal, meny, oda
from scraper.db import close_pool, fetch_active_products, update_ean, upsert_prices

log = structlog.get_logger(__name__)


async def run() -> None:
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.KeyValueRenderer(key_order=["event"]),
        ],
    )

    log.info("scraper_start")
    products = await fetch_active_products()
    log.info("products_loaded", count=len(products))

    # Primary: Kassal (name-based search, returns real EANs)
    kassal_rows, ean_corrections = await kassal.fetch_prices_batch(products)

    # Apply EAN corrections back to the DB so future runs use real EANs
    for old_ean, new_ean, base_price in ean_corrections:
        log.info("ean_correction", old=old_ean, new=new_ean)
        await update_ean(old_ean, new_ean, base_price)

    # Build a set of EANs that got a Kassal price
    covered_eans = {r["db_ean"] for r in kassal_rows}
    missing = [p for p in products if p["ean"] not in covered_eans]
    log.info("kassal_coverage", covered=len(covered_eans), missing=len(missing))

    # Fallback 1: Oda
    oda_rows: list[dict] = []
    if missing:
        missing_eans = [p["ean"] for p in missing]
        oda_rows = await oda.fetch_prices_batch(missing_eans)
        covered_oda = {r["ean"] for r in oda_rows}
        missing = [p for p in missing if p["ean"] not in covered_oda]

    # Fallback 2: Meny
    meny_rows: list[dict] = []
    if missing:
        meny_rows = await meny.fetch_prices_batch([p["ean"] for p in missing])

    # Strip internal db_ean key before insert
    all_rows = [
        {k: v for k, v in r.items() if k != "db_ean"}
        for r in kassal_rows + oda_rows + meny_rows
    ]
    inserted = await upsert_prices(all_rows)
    log.info("scraper_done", total_rows=inserted)

    await close_pool()


def main() -> None:
    try:
        asyncio.run(run())
    except Exception:
        log.exception("scraper_fatal")
        sys.exit(1)


if __name__ == "__main__":
    main()
