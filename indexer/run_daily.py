"""CLI entry point to compute daily_index for today (or a given date).

Usage:
    python -m indexer.run_daily
    python -m indexer.run_daily --date 2026-04-15
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import date

import asyncpg
import structlog

from indexer.laspeyres import compute_and_store
from scraper.config import settings

log = structlog.get_logger(__name__)


async def run(target_date: date) -> None:
    pool = await asyncpg.create_pool(settings.database_url)
    await compute_and_store(pool, target_date)
    await pool.close()
    log.info("indexer_done", date=target_date)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    target = date.fromisoformat(args.date)
    asyncio.run(run(target))


if __name__ == "__main__":
    main()
