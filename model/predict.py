"""Monthly nowcast: runs on the 1st, predicts the SSB print on ~the 10th.

Outputs a point estimate + 95% CI stored in the `nowcast` table.

Usage:
    python -m model.predict
"""
from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta
from pathlib import Path

import asyncpg
import numpy as np
import pandas as pd
import structlog
import xgboost as xgb

from model.features import build_feature_row, fetch_eurnok
from scraper.config import settings

log = structlog.get_logger(__name__)

MODEL_PATH = Path("model/artifacts/xgb_latest.json")
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
    rng = np.random.default_rng(0)
    preds = []
    for _ in range(n):
        noise = rng.normal(0, 0.3, size=X_row.shape)  # ±0.3pp noise per feature
        preds.append(float(model.predict(X_row.values + noise)[0]))
    preds_arr = np.array(preds)
    return float(np.percentile(preds_arr, 2.5)), float(np.percentile(preds_arr, 97.5))


async def run(target_month: date | None = None) -> None:
    if target_month is None:
        today = date.today()
        target_month = today.replace(day=1)

    log.info("nowcast_start", target_month=target_month)

    model = xgb.XGBRegressor()
    model.load_model(MODEL_PATH)

    pool = await asyncpg.create_pool(settings.database_url)

    # Load daily_index for the current month
    rows = await pool.fetch(
        "SELECT price_date, coicop_code, index_value, mom_pct, raw_volatility FROM daily_index"
        " WHERE price_date >= $1 ORDER BY price_date",
        target_month,
    )
    daily_df = pd.DataFrame([dict(r) for r in rows])
    daily_df["price_date"] = pd.to_datetime(daily_df["price_date"])

    # Load raw prices for promo intensity
    price_rows = await pool.fetch(
        "SELECT price_date, is_promo FROM raw_prices WHERE price_date >= $1",
        target_month,
    )
    price_df = pd.DataFrame([dict(r) for r in price_rows])
    if not price_df.empty:
        price_df["price_date"] = pd.to_datetime(price_df["price_date"])

    # Fetch EUR/NOK
    prev_month_start = (target_month - timedelta(days=1)).replace(day=1)
    eurnok_mom = await fetch_eurnok(
        str(prev_month_start), str(target_month - timedelta(days=1))
    )

    feat = build_feature_row(daily_df, price_df, target_month, eurnok_mom)
    X = pd.DataFrame([feat])[FEATURE_COLS].fillna(0.0)

    point = float(model.predict(X)[0])
    ci_lo, ci_hi = _bootstrap_ci(model, X)

    log.info(
        "nowcast_result",
        point=round(point, 3),
        ci_lo=round(ci_lo, 3),
        ci_hi=round(ci_hi, 3),
    )

    await pool.execute(
        """
        INSERT INTO nowcast (run_date, target_month, point_estimate, ci_lower_95, ci_upper_95, model_version, features_json)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (run_date) DO UPDATE SET
            point_estimate = EXCLUDED.point_estimate,
            ci_lower_95    = EXCLUDED.ci_lower_95,
            ci_upper_95    = EXCLUDED.ci_upper_95,
            features_json  = EXCLUDED.features_json
        """,
        date.today(),
        target_month,
        point,
        ci_lo,
        ci_hi,
        MODEL_PATH.stem,
        json.dumps({k: (None if isinstance(v, float) and v != v else v) for k, v in feat.items()}, default=str),
    )
    await pool.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
