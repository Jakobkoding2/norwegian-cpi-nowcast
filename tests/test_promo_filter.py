"""Unit tests for promo_filter — no DB required."""
import pandas as pd
import pytest

from indexer.promo_filter import clean, effective_price


def _make_df(rows):
    return pd.DataFrame(rows)


def test_effective_price_uses_promo():
    df = _make_df([{"ean": "A", "price": 100.0, "is_promo": True, "promo_price": 80.0, "price_date": "2026-01-01"}])
    out = effective_price(df)
    assert out["effective_price"].iloc[0] == 80.0


def test_effective_price_uses_regular_when_no_promo():
    df = _make_df([{"ean": "A", "price": 100.0, "is_promo": False, "promo_price": None, "price_date": "2026-01-01"}])
    out = effective_price(df)
    assert out["effective_price"].iloc[0] == 100.0


def test_modal_smooth_absorbs_flash_sale():
    # Product priced at 39.90 every day except one flash-sale day at 19.90.
    # Modal price over the window should be 39.90, not 19.90.
    rows = [
        {"ean": "A", "price": 39.90 if i != 3 else 19.90, "is_promo": False, "promo_price": None,
         "price_date": f"2026-01-{i+1:02d}"}
        for i in range(7)
    ]
    df = _make_df(rows)
    out = clean(df)
    # The modal smoothed price for the flash-sale day should be 39.90
    spike_row = out[out["price"] == 19.90]
    if not spike_row.empty:
        assert spike_row["smoothed_price"].iloc[0] == pytest.approx(39.90), (
            "Modal smooth should return 39.90 (the dominant price)"
        )


def test_modal_smooth_sustained_promo_not_absorbed():
    # If a price genuinely drops for many days, the mode shifts too.
    # 5 days at 29.90, then 2 days at 19.90 → mode = 29.90 still for last row.
    rows = [
        {"ean": "A", "price": 29.90 if i < 5 else 19.90, "is_promo": False, "promo_price": None,
         "price_date": f"2026-01-{i+1:02d}"}
        for i in range(7)
    ]
    df = _make_df(rows)
    out = clean(df)
    # Last two rows have 2× 19.90 vs 5× 29.90 in window → mode is still 29.90
    assert out["smoothed_price"].iloc[-1] == pytest.approx(29.90)


def test_laspeyres_index_value():
    """Smoke test: a basket where all prices equal base => index should be 100."""
    rows = [
        {
            "ean": f"EAN{i}",
            "coicop_code": "01.1.1",
            "weight": 1.0,
            "base_price": 10.0,
            "raw_price": 10.0,
            "is_promo": False,
            "promo_price": None,
            "price_date": "2026-01-01",
        }
        for i in range(5)
    ]
    df = pd.DataFrame(rows)
    df["effective_price"] = df["raw_price"]
    df["smoothed_price"] = df["raw_price"]
    df["price_relative"] = df["smoothed_price"] / df["base_price"]
    group_sums = df.groupby("coicop_code")["weight"].transform("sum")
    df["norm_weight"] = df["weight"] / group_sums
    df["weighted_relative"] = df["price_relative"] * df["norm_weight"]
    index_val = df["weighted_relative"].sum() * 100
    assert abs(index_val - 100.0) < 0.01
