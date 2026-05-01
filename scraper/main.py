"""Entry point for the daily price ingestion pipeline.

Run at 02:00 daily via GitHub Actions or Docker cron.
Strategy:
  1. Fetch all active EANs from the DB.
  2. Hit Kassal API (primary — cheapest, fastest).
  3. For any EAN that returned no price, fall back to Oda then Meny.
  4. Write everything to raw_prices (idempotent).
  5. Trigger the indexer to recompute today's daily_index.
"""
from __future__ import annotations

import asyncio
import sys

import structlog

from scraper import kassal, meny, oda
from scraper.db import close_pool, fetch_active_eans, upsert_prices

log = structlog.get_logger(__name__)


async def run() -> None:
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
    )

    log.info("scraper_start")
    eans = await fetch_active_eans()
    log.info("eans_loaded", count=len(eans))

    # Primary: Kassal
    kassal_rows = await kassal.fetch_prices_batch(eans)
    covered = {r["ean"] for r in kassal_rows}
    missing = [e for e in eans if e not in covered]
    log.info("kassal_coverage", covered=len(covered), missing=len(missing))

    # Fallback 1: Oda
    oda_rows: list[dict] = []
    if missing:
        oda_rows = await oda.fetch_prices_batch(missing)
        covered_oda = {r["ean"] for r in oda_rows}
        missing = [e for e in missing if e not in covered_oda]

    # Fallback 2: Meny
    meny_rows: list[dict] = []
    if missing:
        meny_rows = await meny.fetch_prices_batch(missing)

    all_rows = kassal_rows + oda_rows + meny_rows
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
