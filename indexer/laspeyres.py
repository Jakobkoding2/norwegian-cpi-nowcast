"""Laspeyres price index engine.

Formula (per COICOP group):
    I_t = Σ_i [ w_i * (P_it / P_i0) ]  ×  100

where:
    w_i   = SSB basket weight (normalised to 1.0 within each COICOP group)
    P_it  = smoothed price on date t
    P_i0  = base price (Jan 2026 reference month, stored in products.base_price_p0)

Output rows are written to the daily_index table.
"""
from __future__ import annotations

import asyncpg
import pandas as pd
import structlog

log = structlog.get_logger(__name__)


async def compute_and_store(pool: asyncpg.Pool, price_date: "date") -> None:  # type: ignore[name-defined]
    from datetime import date  # noqa: PLC0415

    # Pull smoothed prices for today joined with product weights & base prices
    query = """
        SELECT
            p.ean,
            p.coicop_code,
            p.ssb_weight_2026    AS weight,
            p.base_price_p0      AS base_price,
            rp.price             AS raw_price,
            rp.is_promo,
            rp.promo_price
        FROM raw_prices rp
        JOIN products p ON p.ean = rp.ean
        WHERE rp.price_date = $1
          AND p.active = TRUE
    """
    rows = await pool.fetch(query, price_date)
    if not rows:
        log.warning("no_prices_for_date", date=price_date)
        return

    df = pd.DataFrame([dict(r) for r in rows])

    # Apply promo smoothing inline (need historical window — fetch last 7 days)
    hist_query = """
        SELECT rp.ean, rp.price_date, rp.price, rp.is_promo, rp.promo_price
        FROM raw_prices rp
        JOIN products p ON p.ean = rp.ean
        WHERE rp.price_date BETWEEN ($1::date - INTERVAL '7 days') AND $1
          AND p.active = TRUE
        ORDER BY rp.ean, rp.price_date
    """
    hist_rows = await pool.fetch(hist_query, price_date)
    hist_df = pd.DataFrame([dict(r) for r in hist_rows])

    from indexer.promo_filter import clean  # noqa: PLC0415
    hist_clean = clean(hist_df)

    today_smoothed = (
        hist_clean[hist_clean["price_date"] == price_date]
        .groupby("ean")["smoothed_price"]
        .first()
        .reset_index()
    )

    df = df.merge(today_smoothed, on="ean", how="left")
    df["smoothed_price"] = df["smoothed_price"].fillna(df["raw_price"])

    # Price relatives
    df["price_relative"] = df["smoothed_price"] / df["base_price"]

    # Normalise weights within each COICOP group so they sum to 1
    group_weight_sums = df.groupby("coicop_code")["weight"].transform("sum")
    df["norm_weight"] = df["weight"] / group_weight_sums

    df["weighted_relative"] = df["price_relative"] * df["norm_weight"]

    # Aggregate to COICOP group level
    grp = df.groupby("coicop_code").agg(
        index_value=("weighted_relative", "sum"),
        raw_volatility=("price_relative", "std"),
        n_products=("ean", "count"),
    ).reset_index()

    grp["index_value"] = grp["index_value"] * 100  # express as index (base=100)

    # Compute MoM: compare to same COICOP group on first day of previous month
    # (simplified: compare to 30 days ago if present)
    prev_query = """
        SELECT coicop_code, index_value
        FROM daily_index
        WHERE price_date = ($1::date - INTERVAL '30 days')
    """
    prev_rows = await pool.fetch(prev_query, price_date)
    if prev_rows:
        prev_df = pd.DataFrame([dict(r) for r in prev_rows])
        grp = grp.merge(prev_df.rename(columns={"index_value": "prev_index"}), on="coicop_code", how="left")
        grp["mom_pct"] = (grp["index_value"] - grp["prev_index"]) / grp["prev_index"] * 100
    else:
        grp["mom_pct"] = None

    # Upsert into daily_index
    upsert_q = """
        INSERT INTO daily_index (price_date, coicop_code, index_value, mom_pct, raw_volatility, n_products)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (price_date, coicop_code)
        DO UPDATE SET
            index_value    = EXCLUDED.index_value,
            mom_pct        = EXCLUDED.mom_pct,
            raw_volatility = EXCLUDED.raw_volatility,
            n_products     = EXCLUDED.n_products
    """
    for _, row in grp.iterrows():
        await pool.execute(
            upsert_q,
            price_date,
            row["coicop_code"],
            float(row["index_value"]),
            float(row["mom_pct"]) if pd.notna(row.get("mom_pct")) else None,
            float(row["raw_volatility"]) if pd.notna(row.get("raw_volatility")) else None,
            int(row["n_products"]),
        )

    log.info("index_computed", date=price_date, coicop_groups=len(grp))
