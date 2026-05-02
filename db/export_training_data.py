"""Export training data CSV for the XGBoost nowcast model.

Joins ssb_official (target) with daily_index features (internal index MoM,
promo intensity, volatility) and Norges Bank EUR/NOK historical rates.

For months before daily_index collection began, internal features are left
as NaN — model/train.py fills them with the column median at training time.
The seasonal flags (is_feb_window, is_jul_window) are always available since
they are derived from the calendar.

Usage:
    python -m db.export_training_data
    python -m db.export_training_data --output model/artifacts/training_data.csv
    python -m db.export_training_data --from 2020-01  # limit historical range
"""
from __future__ import annotations

import argparse
import asyncio
import os
from datetime import date
from pathlib import Path

import asyncpg
import httpx
import pandas as pd
import structlog

log = structlog.get_logger(__name__)

DATABASE_URL = os.environ["DATABASE_URL"]

NORGES_BANK_URL = (
    "https://data.norges-bank.no/api/data/EXR/B.EUR.NOK.SP"
    "?format=sdmx-json&startPeriod={start}&endPeriod={end}&locale=en"
)


async def _fetch_eurnok_history(start: str, end: str) -> pd.DataFrame:
    """Return a DataFrame with columns [year_month, eurnok_rate]."""
    url = NORGES_BANK_URL.format(start=start, end=end)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()

    obs = data["data"]["dataSets"][0]["series"]["0:0:0:0"]["observations"]
    periods = data["data"]["structure"]["dimensions"]["observation"][0]["values"]

    records = []
    for key, vals in obs.items():
        idx = int(key)
        period_id = periods[idx]["id"]  # e.g. "2024-01-15"
        rate = vals[0]
        if rate is not None:
            records.append({"obs_date": pd.to_datetime(period_id), "rate": float(rate)})

    df = pd.DataFrame(records).sort_values("obs_date")
    # Resample to monthly mean
    df = df.set_index("obs_date").resample("MS")["rate"].mean().reset_index()
    df.rename(columns={"obs_date": "month"}, inplace=True)
    return df


async def export(output: str, from_month: str) -> None:
    pool = await asyncpg.create_pool(DATABASE_URL)

    # ── SSB actuals ──────────────────────────────────────────────────────────
    ssb_rows = await pool.fetch(
        "SELECT reference_month, mom_pct FROM ssb_official "
        "WHERE reference_month >= $1 ORDER BY reference_month",
        date.fromisoformat(from_month + "-01"),
    )
    ssb_df = pd.DataFrame([dict(r) for r in ssb_rows])
    ssb_df["reference_month"] = pd.to_datetime(ssb_df["reference_month"])
    ssb_df["mom_pct"] = ssb_df["mom_pct"].apply(float)
    log.info("ssb_loaded", rows=len(ssb_df))

    # ── Internal daily index features ─────────────────────────────────────────
    # Use data through day 21 of each target month (matches SSB collection window)
    idx_rows = await pool.fetch(
        """
        SELECT price_date, mom_pct, raw_volatility, is_feb_window, is_jul_window
        FROM daily_index
        WHERE price_date >= $1
        ORDER BY price_date
        """,
        date.fromisoformat(from_month + "-01"),
    )
    idx_df = pd.DataFrame([dict(r) for r in idx_rows])
    if not idx_df.empty:
        idx_df["price_date"] = pd.to_datetime(idx_df["price_date"])
        idx_df["mom_pct"] = idx_df["mom_pct"].apply(lambda v: float(v) if v is not None else None)
        idx_df["raw_volatility"] = idx_df["raw_volatility"].apply(
            lambda v: float(v) if v is not None else None
        )
        idx_df["month"] = idx_df["price_date"].dt.to_period("M").dt.to_timestamp()
        # Restrict to first 21 days
        idx_df = idx_df[idx_df["price_date"].dt.day <= 21]
        internal = idx_df.groupby("month").agg(
            internal_mom_pct=("mom_pct", "mean"),
            volatility_mean=("raw_volatility", "mean"),
            is_feb_window=("is_feb_window", "first"),
            is_jul_window=("is_jul_window", "first"),
        ).reset_index()
    else:
        internal = pd.DataFrame(columns=["month", "internal_mom_pct", "volatility_mean",
                                          "is_feb_window", "is_jul_window"])

    # ── Promo intensity from raw_prices ───────────────────────────────────────
    promo_rows = await pool.fetch(
        """
        SELECT price_date, is_promo FROM raw_prices
        WHERE price_date >= $1 AND EXTRACT(day FROM price_date) <= 21
        """,
        date.fromisoformat(from_month + "-01"),
    )
    if promo_rows:
        promo_df = pd.DataFrame([dict(r) for r in promo_rows])
        promo_df["price_date"] = pd.to_datetime(promo_df["price_date"])
        promo_df["month"] = promo_df["price_date"].dt.to_period("M").dt.to_timestamp()
        promo_agg = promo_df.groupby("month")["is_promo"].mean().reset_index()
        promo_agg.rename(columns={"is_promo": "promo_intensity"}, inplace=True)
    else:
        promo_agg = pd.DataFrame(columns=["month", "promo_intensity"])

    await pool.close()

    # ── EUR/NOK from Norges Bank ───────────────────────────────────────────────
    eurnok_df = await _fetch_eurnok_history(from_month, str(date.today()))
    eurnok_df["eur_nok_mom_pct"] = eurnok_df["rate"].pct_change() * 100
    log.info("eurnok_loaded", rows=len(eurnok_df))

    # ── Assemble ──────────────────────────────────────────────────────────────
    result = ssb_df.rename(columns={"reference_month": "month", "mom_pct": "ssb_mom_pct"})
    result = result.merge(eurnok_df[["month", "eur_nok_mom_pct"]], on="month", how="left")
    result = result.merge(internal, on="month", how="left")
    result = result.merge(promo_agg, on="month", how="left")

    # Derive seasonal flags for historical months lacking daily_index data
    if "is_feb_window" not in result.columns or result["is_feb_window"].isna().any():
        result["is_feb_window"] = result["month"].dt.month.isin([1, 2]).astype(int)
    if "is_jul_window" not in result.columns or result["is_jul_window"].isna().any():
        result["is_jul_window"] = result["month"].dt.month.isin([6, 7]).astype(int)

    result["target_month"] = result["month"].dt.date
    out_cols = [
        "target_month", "ssb_mom_pct",
        "internal_mom_pct", "eur_nok_mom_pct",
        "promo_intensity", "volatility_mean",
        "is_feb_window", "is_jul_window",
    ]
    result = result[out_cols].sort_values("target_month")

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False)
    log.info("training_data_exported", rows=len(result), path=output,
             with_internal=int(result["internal_mom_pct"].notna().sum()))
    print(f"\nExported {len(result)} rows -> {output}")
    print(f"  Rows with internal index data : {result['internal_mom_pct'].notna().sum()}")
    print(f"  Rows with EUR/NOK data        : {result['eur_nok_mom_pct'].notna().sum()}")
    print("\nLast 6 rows:")
    print(result.tail(6).to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="model/artifacts/training_data.csv")
    parser.add_argument("--from", dest="from_month", default="2010-01",
                        help="Start month YYYY-MM (default: 2010-01)")
    args = parser.parse_args()
    asyncio.run(export(args.output, args.from_month))


if __name__ == "__main__":
    main()
