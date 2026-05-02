"""Backfill historical nowcast predictions using the trained XGBoost model.

For every month in ssb_official (or the training CSV), runs the model with
features available *before* SSB publishes (~10th of following month):
  - is_feb_window / is_jul_window  (calendar)
  - eur_nok_mom_pct                (Norges Bank historical)
  - internal_mom_pct               (our live index — NaN for pre-May 2026)
  - promo_intensity                (NaN for pre-May 2026)
  - volatility_mean                (NaN for pre-May 2026)

Results are stored in the nowcast table with run_date = target_month
(i.e. the 1st of each month) so they don't conflict with live runs
(which use run_date = today).

Usage:
    python -m model.backfill_predictions
    python -m model.backfill_predictions --from 2020-01
    python -m model.backfill_predictions --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import date
from pathlib import Path

import asyncpg
import numpy as np
import pandas as pd
import structlog
import xgboost as xgb

log = structlog.get_logger(__name__)

MODEL_PATH = Path("model/artifacts/xgb_latest.json")
TRAINING_CSV = Path("model/artifacts/training_data.csv")

FEATURE_COLS = [
    "internal_mom_pct",
    "eur_nok_mom_pct",
    "promo_intensity",
    "volatility_mean",
    "is_feb_window",
    "is_jul_window",
]

BOOTSTRAP_ROUNDS = 1000


def _bootstrap_ci(
    model: xgb.XGBRegressor,
    X_row: pd.DataFrame,
    n: int = BOOTSTRAP_ROUNDS,
) -> tuple[float, float]:
    """Rough 95% CI via feature perturbation bootstrap."""
    rng = np.random.default_rng(42)
    preds = []
    for _ in range(n):
        noise = rng.normal(0, 0.3, size=X_row.shape)
        preds.append(float(model.predict(X_row.values + noise)[0]))
    arr = np.array(preds)
    return float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))


async def run(from_month: str = "2010-01", dry_run: bool = False) -> None:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Model not found at {MODEL_PATH}. Run python -m model.train first."
        )
    if not TRAINING_CSV.exists():
        raise FileNotFoundError(
            f"Training CSV not found at {TRAINING_CSV}. "
            "Run python -m db.export_training_data first."
        )

    model = xgb.XGBRegressor()
    model.load_model(MODEL_PATH)
    log.info("model_loaded", path=str(MODEL_PATH))

    df = pd.read_csv(TRAINING_CSV, parse_dates=["target_month"])
    df = df[df["target_month"] >= pd.Timestamp(from_month + "-01")]
    df = df.sort_values("target_month").reset_index(drop=True)
    log.info("training_csv_loaded", rows=len(df))

    # Fill seasonal flags from calendar where missing
    df["is_feb_window"] = df["is_feb_window"].fillna(
        df["target_month"].dt.month.isin([1, 2]).astype(int)
    )
    df["is_jul_window"] = df["is_jul_window"].fillna(
        df["target_month"].dt.month.isin([6, 7]).astype(int)
    )

    DATABASE_URL = os.environ["DATABASE_URL"]
    pool = await asyncpg.create_pool(DATABASE_URL)

    inserted = 0
    skipped = 0

    for _, row in df.iterrows():
        target_month: date = row["target_month"].date()
        run_date = target_month  # use 1st of month as run_date for backfill

        feat = {col: (None if pd.isna(row.get(col)) else float(row[col])) for col in FEATURE_COLS}
        X = pd.DataFrame([feat])[FEATURE_COLS].fillna(0.0)

        point = float(model.predict(X)[0])
        ci_lo, ci_hi = _bootstrap_ci(model, X)

        feat_json = {k: v for k, v in feat.items()}

        if dry_run:
            print(
                f"  {target_month}  point={point:+.3f}%  CI=[{ci_lo:+.3f}, {ci_hi:+.3f}]"
            )
            inserted += 1
            continue

        await pool.execute(
            """
            INSERT INTO nowcast
                (run_date, target_month, point_estimate, ci_lower_95, ci_upper_95,
                 model_version, features_json)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (run_date) DO UPDATE SET
                point_estimate = EXCLUDED.point_estimate,
                ci_lower_95    = EXCLUDED.ci_lower_95,
                ci_upper_95    = EXCLUDED.ci_upper_95,
                features_json  = EXCLUDED.features_json
            """,
            run_date,
            target_month,
            point,
            ci_lo,
            ci_hi,
            MODEL_PATH.stem + "_backfill",
            json.dumps(feat_json, default=str),
        )
        inserted += 1

    await pool.close()
    action = "would insert/update" if dry_run else "inserted/updated"
    log.info("backfill_done", action=action, rows=inserted, skipped=skipped)
    print(f"\n✓ Backfill complete: {action} {inserted} nowcast rows.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill historical nowcast predictions")
    parser.add_argument(
        "--from", dest="from_month", default="2010-01",
        help="Start month YYYY-MM (default: 2010-01)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print predictions without writing to DB",
    )
    args = parser.parse_args()
    asyncio.run(run(from_month=args.from_month, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
