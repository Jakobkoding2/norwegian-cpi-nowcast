"""Fetch historical SSB food CPI prints and populate ssb_official table.

Uses SSB's JSON-stat API (table 03013 — KPI, food sub-index, monthly).
Fetches both MoM (Manedsendring) and YoY (Tolvmanedersendring) in one pass.
Run once to bootstrap training data; re-run monthly to pick up new prints.

Usage:
    python -m db.fetch_ssb_history
"""
from __future__ import annotations

import asyncio
import os
from datetime import date

import asyncpg
import httpx

DATABASE_URL = os.environ["DATABASE_URL"]

SSB_URL = "https://data.ssb.no/api/v0/no/table/03013"

# Single query for both MoM and YoY changes for the food group
FOOD_QUERY = {
    "query": [
        {
            "code": "Konsumgrp",
            "selection": {"filter": "item", "values": ["01"]},
        },
        {
            "code": "ContentsCode",
            "selection": {
                "filter": "item",
                "values": ["Manedsendring", "Tolvmanedersendring"],
            },
        },
        {
            "code": "Tid",
            "selection": {"filter": "all", "values": ["*"]},
        },
    ],
    "response": {"format": "json-stat2"},
}


def _parse_jsonstat(data: dict) -> list[dict]:
    """Parse SSB JSON-stat2 response into list of {reference_month, mom_pct, yoy_pct}."""
    dims = data.get("dimension", {})
    time_labels = list(dims["Tid"]["category"]["label"].values())
    stat_ids = list(dims["ContentsCode"]["category"]["index"].keys())

    values = data.get("value", [])
    n_times = len(time_labels)
    n_stats = len(stat_ids)

    # JSON-stat2 layout: values are in row-major order over [ContentsCode, Tid]
    mom_idx = stat_ids.index("Manedsendring") if "Manedsendring" in stat_ids else None
    yoy_idx = stat_ids.index("Tolvmanedersendring") if "Tolvmanedersendring" in stat_ids else None

    results = []
    for t_i, label in enumerate(time_labels):
        try:
            year, month = int(label[:4]), int(label[5:7])
            ref_month = date(year, month, 1)
        except (ValueError, IndexError):
            continue

        mom = values[mom_idx * n_times + t_i] if mom_idx is not None else None
        yoy = values[yoy_idx * n_times + t_i] if yoy_idx is not None else None

        if mom is None:
            continue
        results.append({
            "reference_month": ref_month,
            "mom_pct": float(mom),
            "yoy_pct": float(yoy) if yoy is not None else None,
        })

    return results


async def fetch_and_store() -> None:
    print("Fetching SSB table 03013 — food MoM + YoY CPI (group 01)...")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(SSB_URL, json=FOOD_QUERY)
        if resp.status_code != 200:
            print(f"SSB API returned {resp.status_code}: {resp.text[:300]}")
            return
        data = resp.json()

    records = _parse_jsonstat(data)
    if not records:
        print("No records parsed from SSB response.")
        return

    print(f"Parsed {len(records)} monthly records.")

    pool = await asyncpg.create_pool(DATABASE_URL)
    inserted = updated = 0
    for r in records:
        result = await pool.execute(
            """
            INSERT INTO ssb_official (reference_month, mom_pct, yoy_pct, published_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (reference_month) DO UPDATE
                SET mom_pct = EXCLUDED.mom_pct,
                    yoy_pct = EXCLUDED.yoy_pct
            """,
            r["reference_month"],
            r["mom_pct"],
            r["yoy_pct"],
            r["reference_month"],
        )
        if result == "INSERT 0 1":
            inserted += 1
        else:
            updated += 1

    await pool.close()
    print(f"Inserted {inserted} new, updated {updated} existing SSB records.")

    print("\nLast 6 months:")
    for r in sorted(records, key=lambda x: x["reference_month"])[-6:]:
        yoy = f"  YoY {r['yoy_pct']:+.1f}%" if r["yoy_pct"] is not None else ""
        print(f"  {r['reference_month']}  MoM {r['mom_pct']:+.2f}%{yoy}")


if __name__ == "__main__":
    asyncio.run(fetch_and_store())
