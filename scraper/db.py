"""Async database helpers using asyncpg directly for bulk inserts."""
from __future__ import annotations

import asyncpg

from scraper.config import settings

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(settings.database_url, min_size=2, max_size=10)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def fetch_active_products() -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch("SELECT ean, name, base_price_p0 FROM products WHERE active = TRUE")
    return [dict(r) for r in rows]


async def fetch_active_eans() -> list[str]:
    pool = await get_pool()
    rows = await pool.fetch("SELECT ean FROM products WHERE active = TRUE")
    return [r["ean"] for r in rows]


async def update_ean(old_ean: str, new_ean: str, base_price: float) -> None:
    pool = await get_pool()
    await pool.execute(
        "UPDATE products SET ean = $1, base_price_p0 = $2 WHERE ean = $3",
        new_ean, base_price, old_ean,
    )


async def upsert_prices(records: list[dict]) -> int:
    """Bulk-insert price rows; skips duplicates via ON CONFLICT DO NOTHING."""
    if not records:
        return 0
    pool = await get_pool()
    query = """
        INSERT INTO raw_prices (ean, price_date, price, is_promo, promo_price, source)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (ean, price_date, source) DO NOTHING
    """
    rows = [
        (
            r["ean"],
            r["price_date"],
            r["price"],
            r.get("is_promo", False),
            r.get("promo_price"),
            r["source"],
        )
        for r in records
    ]
    await pool.executemany(query, rows)
    return len(rows)
