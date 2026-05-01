"""Laspeyres price index engine.

Formula (per COICOP group):
    I_t = Σ_i [ w_i * (P_it / P_i0) ]  ×  100

where:
    w_i   = SSB basket weight (normalised to 1.0 within each COICOP group)
    P_it  = modal-smoothed price on date t (or forward-filled from most recent day)
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

    # Fetch 30-day price history — covers the modal smoothing window and provides
    # the source data for forward-filling products that missed today's scrape.
    hist_query = """
        SELECT rp.ean, rp.price_date, rp.price, rp.is_promo, rp.promo_price
        FROM raw_prices rp
        JOIN products p ON p.ean = rp.ean
        WHERE rp.price_date BETWEEN ($1::date - INTERVAL '30 days') AND $1
          AND p.active = TRUE
        ORDER BY rp.ean, rp.price_date
    """
    hist_rows = await pool.fetch(hist_query, price_date)
    if not hist_rows:
        log.warning("no_prices_in_30d_window", date=price_date)
        return

    hist_df = pd.DataFrame([dict(r) for r in hist_rows])
    for col in ("price", "promo_price"):
        if col in hist_df.columns:
            hist_df[col] = hist_df[col].apply(lambda v: float(v) if v is not None else None)

    from indexer.promo_filter import clean  # noqa: PLC0415
    hist_clean = clean(hist_df)

    # Today's modal-smoothed price per EAN
    today_smoothed = (
        hist_clean[hist_clean["price_date"] == price_date]
        .groupby("ean")["smoothed_price"]
        .first()
        .reset_index()
    )

    # Forward-fill: active products with no scrape today get their most recent
    # modal-smoothed price carried forward (avoids dropping basket coverage on
    # days when the scraper misses a product).
    prod_rows = await pool.fetch("SELECT ean FROM products WHERE active = TRUE")
    all_active_eans = {r["ean"] for r in prod_rows}
    today_eans = set(today_smoothed["ean"])
    missing_eans = all_active_eans - today_eans

    if missing_eans:
        ff = (
            hist_clean[hist_clean["ean"].isin(missing_eans)]
            .sort_values("price_date")
            .groupby("ean")["smoothed_price"]
            .last()
            .reset_index()
        )
        if not ff.empty:
            today_smoothed = pd.concat([today_smoothed, ff], ignore_index=True)
            log.info("forward_filled", n=len(ff), date=price_date)

    # Join smoothed prices with product metadata
    ean_list = list(today_smoothed["ean"])
    prod_meta_rows = await pool.fetch(
        """
        SELECT ean, coicop_code,
               ssb_weight_2026 AS weight,
               base_price_p0   AS base_price
        FROM products
        WHERE ean = ANY($1::varchar[]) AND active = TRUE
        """,
        ean_list,
    )
    prod_df = pd.DataFrame([dict(r) for r in prod_meta_rows])
    for col in ("weight", "base_price"):
        prod_df[col] = prod_df[col].apply(lambda v: float(v) if v is not None else None)

    df = today_smoothed.merge(prod_df, on="ean", how="inner")
    if df.empty:
        log.warning("no_products_after_merge", date=price_date)
        return

    # Sanity cap: drop smoothed prices > 5× COICOP group median (Kassal unit-price errors)
    group_medians = df.groupby("coicop_code")["smoothed_price"].transform("median")
    df = df[df["smoothed_price"] <= group_medians * 5].copy()
    if df.empty:
        log.warning("all_prices_filtered_as_outliers", date=price_date)
        return

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
    grp["index_value"] = grp["index_value"] * 100

    # Seasonal window flags — stored so the model can use them as features directly
    month = price_date.month
    grp["is_feb_window"] = month in (1, 2)
    grp["is_jul_window"] = month in (6, 7)

    # MoM: compare to same COICOP group 30 days ago
    prev_rows = await pool.fetch(
        "SELECT coicop_code, index_value FROM daily_index WHERE price_date = ($1::date - INTERVAL '30 days')",
        price_date,
    )
    if prev_rows:
        prev_df = pd.DataFrame([dict(r) for r in prev_rows])
        grp = grp.merge(prev_df.rename(columns={"index_value": "prev_index"}), on="coicop_code", how="left")
        grp["mom_pct"] = (grp["index_value"] - grp["prev_index"]) / grp["prev_index"] * 100
    else:
        grp["mom_pct"] = None

    # Upsert into daily_index
    upsert_q = """
        INSERT INTO daily_index
            (price_date, coicop_code, index_value, mom_pct, raw_volatility, n_products,
             is_feb_window, is_jul_window)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (price_date, coicop_code)
        DO UPDATE SET
            index_value    = EXCLUDED.index_value,
            mom_pct        = EXCLUDED.mom_pct,
            raw_volatility = EXCLUDED.raw_volatility,
            n_products     = EXCLUDED.n_products,
            is_feb_window  = EXCLUDED.is_feb_window,
            is_jul_window  = EXCLUDED.is_jul_window
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
            bool(row["is_feb_window"]),
            bool(row["is_jul_window"]),
        )

    log.info("index_computed", date=price_date, coicop_groups=len(grp))
