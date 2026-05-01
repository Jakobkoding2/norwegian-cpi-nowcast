"""Feature engineering for the CPI nowcast model.

Features (all available before SSB publishes on ~the 10th):
    - internal_mom_pct       : MoM % change in our daily index (first 3 weeks)
    - eur_nok_mom_pct        : EUR/NOK exchange rate MoM change (Norges Bank API)
    - diesel_price_mom_pct   : Diesel proxy for transport inflation
    - promo_intensity         : share of basket items on promotion this month
    - volatility_mean         : mean raw_volatility across COICOP groups
"""
from __future__ import annotations

import httpx
import pandas as pd
import structlog

log = structlog.get_logger(__name__)

NORGES_BANK_API = (
    "https://data.norges-bank.no/api/data/EXR/B.EUR.NOK.SP"
    "?format=sdmx-json&startPeriod={start}&endPeriod={end}&locale=en"
)


async def fetch_eurnok(start: str, end: str) -> float | None:
    """Return MoM % change in EUR/NOK spot rate."""
    url = NORGES_BANK_API.format(start=start, end=end)
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(url, timeout=10)
            r.raise_for_status()
            data = r.json()
            obs = data["data"]["dataSets"][0]["series"]["0:0:0:0"]["observations"]
            values = [v[0] for v in obs.values() if v[0] is not None]
            if len(values) < 2:
                return None
            return (values[-1] - values[0]) / values[0] * 100
    except Exception:
        log.exception("eurnok_fetch_failed")
        return None


def build_feature_row(
    daily_index: pd.DataFrame,
    raw_prices: pd.DataFrame,
    target_month: "date",  # type: ignore[name-defined]
    eurnok_mom: float | None,
) -> dict:
    """Build a single feature dict for `target_month`."""
    from datetime import date  # noqa: PLC0415

    month_start = target_month.replace(day=1)
    # Use data through day 21 (mimics SSB's collection window)
    cutoff = target_month.replace(day=21)

    month_data = daily_index[
        (daily_index["price_date"] >= pd.Timestamp(month_start))
        & (daily_index["price_date"] <= pd.Timestamp(cutoff))
    ]

    # Aggregate to scalar monthly MoM
    internal_mom = month_data["mom_pct"].mean() if not month_data.empty else None

    # Promo intensity
    if not raw_prices.empty:
        month_prices = raw_prices[
            (raw_prices["price_date"] >= month_start)
            & (raw_prices["price_date"] <= cutoff)
        ]
        promo_intensity = month_prices["is_promo"].mean() if not month_prices.empty else 0.0
    else:
        promo_intensity = 0.0

    volatility_mean = month_data["raw_volatility"].mean() if not month_data.empty else None

    return {
        "target_month": target_month,
        "internal_mom_pct": internal_mom,
        "eur_nok_mom_pct": eurnok_mom,
        "promo_intensity": promo_intensity,
        "volatility_mean": volatility_mean,
    }
