"""Fetch historical SSB food CPI prints and populate ssb_official table.

Uses SSB's JSON-stat API (table 03013 — KPI, food sub-index, monthly MoM).
Run once to bootstrap training data, then SSB prints are added manually
after each monthly release.

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

# SSB StatBank API — table 03013: Consumer price index, main groups
# We query "Matvarer og alkoholfrie drikkevarer" (food & non-alcoholic beverages)
SSB_URL = "https://data.ssb.no/api/v0/no/table/03013"

# Query for food sub-group MoM — table 03013, group "01" = Matvarer og alkoholfrie drikkevarer
FOOD_QUERY = {
    "query": [
        {
            "code": "Konsumgrp",
            "selection": {
                "filter": "item",
                "values": ["01"],  # Matvarer og alkoholfrie drikkevarer
            },
        },
        {
            "code": "ContentsCode",
            "selection": {"filter": "item", "values": ["Manedsendring"]},  # MoM %
        },
        {
            "code": "Tid",
            "selection": {"filter": "all", "values": ["*"]},
        },
    ],
    "response": {"format": "json-stat2"},
}


def _parse_jsonstat(data: dict) -> list[dict]:
    """Parse SSB JSON-stat2 response into list of {month, mom_pct} dicts."""
    dims = data.get("dimension", {})
    time_dim = dims.get("Tid", {})
    time_labels = list(time_dim.get("category", {}).get("label", {}).values())

    values = data.get("value", [])

    results = []
    for label, val in zip(time_labels, values):
        if val is None:
            continue
        # Label format: "2024M01" → date(2024, 1, 1)
        try:
            year, month = int(label[:4]), int(label[5:7])
            ref_month = date(year, month, 1)
        except (ValueError, IndexError):
            continue
        results.append({"reference_month": ref_month, "mom_pct": float(val)})

    return results


async def fetch_and_store() -> None:
    print("Fetching SSB table 03013 — food MoM CPI (group 01, Manedsendring)...")
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
    inserted = 0
    for r in records:
        result = await pool.execute(
            """
            INSERT INTO ssb_official (reference_month, mom_pct, published_at)
            VALUES ($1, $2, $3)
            ON CONFLICT (reference_month) DO NOTHING
            """,
            r["reference_month"],
            r["mom_pct"],
            r["reference_month"],  # placeholder — real publish date unknown for old data
        )
        if result == "INSERT 0 1":
            inserted += 1

    await pool.close()
    print(f"Inserted {inserted} new SSB records. Total in DB: {len(records)}")

    # Print last 6 months as sanity check
    print("\nLast 6 months:")
    for r in sorted(records, key=lambda x: x["reference_month"])[-6:]:
        print(f"  {r['reference_month']}  {r['mom_pct']:+.2f}%")


if __name__ == "__main__":
    asyncio.run(fetch_and_store())
