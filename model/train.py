"""Train the XGBoost nowcast model on historical data.

Run manually after accumulating ≥12 months of history, then re-run
whenever a new SSB print is available.

Usage:
    python -m model.train --output model/artifacts/xgb_v1.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import TimeSeriesSplit, cross_val_score

FEATURE_COLS = [
    "internal_mom_pct",
    "eur_nok_mom_pct",
    "promo_intensity",
    "volatility_mean",
    "is_feb_window",
    "is_jul_window",
]


def load_training_data(csv_path: str) -> tuple[pd.DataFrame, pd.Series]:
    """Load a CSV with feature columns + `ssb_mom_pct` target."""
    df = pd.read_csv(csv_path, parse_dates=["target_month"])
    df = df.dropna(subset=["ssb_mom_pct"])
    df = df.sort_values("target_month")
    # Derive seasonal flags from target_month if not already present
    if "is_feb_window" not in df.columns:
        df["is_feb_window"] = df["target_month"].dt.month.isin([1, 2]).astype(int)
    if "is_jul_window" not in df.columns:
        df["is_jul_window"] = df["target_month"].dt.month.isin([6, 7]).astype(int)
    X = df[FEATURE_COLS].fillna(df[FEATURE_COLS].median())
    y = df["ssb_mom_pct"]
    return X, y


def train(X: pd.DataFrame, y: pd.Series) -> xgb.XGBRegressor:
    model = xgb.XGBRegressor(
        n_estimators=200,
        max_depth=2,          # shallow trees prevent overfitting on ~50 monthly obs
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=2.0,       # L2 weight regularization (default 1.0)
        min_child_weight=3,   # require ≥3 samples per leaf
        objective="reg:squarederror",
        random_state=42,
    )
    tscv = TimeSeriesSplit(n_splits=5)
    scores = cross_val_score(model, X, y, cv=tscv, scoring="neg_mean_absolute_error")
    print(f"CV MAE: {-scores.mean():.4f} ± {scores.std():.4f}")
    model.fit(X, y)
    return model


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="model/artifacts/training_data.csv")
    parser.add_argument("--output", default="model/artifacts/xgb_latest.json")
    args = parser.parse_args()

    X, y = load_training_data(args.data)
    model = train(X, y)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    model.save_model(args.output)
    print(f"Model saved -> {args.output}")


if __name__ == "__main__":
    main()
