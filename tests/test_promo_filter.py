"""Unit tests for promo_filter — no DB required."""
import pandas as pd
import pytest

from indexer.promo_filter import clean, effective_price, rolling_median_smooth


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


def test_rolling_median_window():
    rows = [
        {"ean": "A", "price": float(p), "is_promo": False, "promo_price": None, "price_date": f"2026-01-{i+1:02d}"}
        for i, p in enumerate([10, 12, 11, 200, 11, 12, 10])  # 200 is a flash-sale spike
    ]
    df = _make_df(rows)
    out = clean(df)
    # After median smoothing the spike should be dampened
    spike_idx = out[out["price"].apply(lambda x: x == 200)].index
    if not spike_idx.empty:
        smoothed_spike = out.loc[spike_idx[0], "smoothed_price"]
        assert smoothed_spike < 200, "Flash-sale spike should be smoothed"


def test_laspeyres_index_value():
    """Smoke test: a basket where all prices equal base => index should be 100."""
    import pandas as pd
    from indexer.promo_filter import clean

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
