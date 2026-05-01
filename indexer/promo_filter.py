"""Promotional noise filtering.

Flash-sale prices distort the signal. Strategy:
- Use promo_price when the item is flagged promotional.
- Apply a 7-day rolling median to absorb single-day spikes.
- Flag rows whose effective price deviates > 2 IQR from the rolling median
  as outliers and replace with the median (handles data errors).
"""
from __future__ import annotations

import pandas as pd


def effective_price(df: pd.DataFrame) -> pd.DataFrame:
    """Add `effective_price` column: promo_price if on promo, else price."""
    df = df.copy()
    df["effective_price"] = df.apply(
        lambda r: r["promo_price"] if r["is_promo"] and pd.notna(r["promo_price"]) else r["price"],
        axis=1,
    )
    return df


def rolling_median_smooth(df: pd.DataFrame, window: int = 7) -> pd.DataFrame:
    """Add `smoothed_price` as 7-day rolling median per EAN."""
    df = df.sort_values(["ean", "price_date"])
    df["smoothed_price"] = (
        df.groupby("ean")["effective_price"]
        .transform(lambda x: x.rolling(window=window, min_periods=1).median())
    )
    return df


def remove_outliers(df: pd.DataFrame, iqr_multiplier: float = 2.0) -> pd.DataFrame:
    """Replace prices more than `iqr_multiplier` IQR from the rolling median with the median."""
    df = df.copy()
    dev = (df["effective_price"] - df["smoothed_price"]).abs()
    q75 = dev.groupby(df["ean"]).transform("quantile", 0.75)
    q25 = dev.groupby(df["ean"]).transform("quantile", 0.25)
    iqr = q75 - q25
    mask = dev > iqr_multiplier * iqr
    df.loc[mask, "effective_price"] = df.loc[mask, "smoothed_price"]
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = effective_price(df)
    df = rolling_median_smooth(df)
    df = remove_outliers(df)
    return df
