"""Promotional noise filtering.

Flash-sale prices distort the signal. Strategy:
- Use promo_price when the item is flagged promotional.
- Apply a 30-day rolling mode to capture the item's true shelf price.
  Unlike a median, the mode is immune to short promotional runs: a product
  sold at 39.90 for 25 out of 30 days will always produce a modal price of
  39.90 regardless of how deep the temporary discount was.
- Flag rows whose effective price deviates > 2 IQR from the modal price
  as outliers and replace with the mode (handles data errors).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def effective_price(df: pd.DataFrame) -> pd.DataFrame:
    """Add `effective_price` column: promo_price if on promo, else price."""
    df = df.copy()
    df["effective_price"] = df.apply(
        lambda r: r["promo_price"] if r["is_promo"] and pd.notna(r["promo_price"]) else r["price"],
        axis=1,
    )
    return df


def modal_smooth(df: pd.DataFrame, window: int = 30) -> pd.DataFrame:
    """Add `smoothed_price` as 30-day rolling mode per EAN.

    For each observation, takes the most frequently occurring price over
    the preceding `window` days. Ties are broken by taking the lower price
    (np.unique returns sorted values, argmax picks the first max-count entry).
    Falls back to the raw effective price when only one observation exists.
    """
    df = df.sort_values(["ean", "price_date"])

    def _rolling_mode(s: pd.Series) -> pd.Series:
        arr = s.to_numpy(dtype=float, na_value=np.nan)
        out = np.empty(len(arr))
        for i in range(len(arr)):
            w = arr[max(0, i - window + 1) : i + 1]
            w = w[~np.isnan(w)]
            if len(w) == 0:
                out[i] = np.nan
            else:
                vals, counts = np.unique(w, return_counts=True)
                out[i] = vals[counts.argmax()]
        return pd.Series(out, index=s.index)

    df["smoothed_price"] = df.groupby("ean")["effective_price"].transform(_rolling_mode)
    return df


def remove_outliers(df: pd.DataFrame, iqr_multiplier: float = 2.0) -> pd.DataFrame:
    """Replace prices more than `iqr_multiplier` IQR from the modal price with the mode."""
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
    df = modal_smooth(df)
    df = remove_outliers(df)
    return df
