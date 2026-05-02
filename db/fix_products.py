"""One-off migration: replace dead/broken products with verified Kassal EANs.

Problems resolved:
  - 8 products that have NEVER returned a price (wrong name, not in Kassal, or
    duplicate of an already-tracked product).
  - Friele Frokostkaffe: correct EAN but name doesn't match Kassal search →
    update name to what Kassal returns.

Run once:
    python -m db.fix_products
"""
from __future__ import annotations

import asyncio
import os

import asyncpg

DATABASE_URL = os.environ["DATABASE_URL"]

# Products to deactivate (EAN → reason)
DEACTIVATE = {
    "7035620054948": (
        "Hatting Loff 750g — not in Kassal; replaced by Coop Toastloff"
    ),
    "7622210951106": (
        "Kjeldsberg Havreflak 750g — product doesn't exist; "
        "replaced by Änglamark Müsli"
    ),
    "7033085041699": (
        "Nortura Kyllingfilet 700g — duplicate Kassal EAN of Coop Kyllingfilet; "
        "replaced by Prior Hel Kylling"
    ),
    "7033085023718": (
        "Nortura Svinekam 1kg — not in Kassal; replaced by Sardiner Ramirez slot"
    ),
    "7311040802001": (
        "Abba Sardiner 125g — not in Kassal; replaced by Sardiner Ramirez"
    ),
    "2000000000015": (
        "Eple Kg — loose-produce EAN, never resolvable; "
        "replaced by Epler 1kg First Price"
    ),
    "2000000000084": (
        "Gulrøtter 750g — loose-produce EAN, duplicate of Gulrot 750g Beger"
    ),
    "7040510605285": (
        "Strøsukker 1kg — not in Kassal; already have 2 sugar products"
    ),
}

# New products to insert
# (ean, name, store_chain, coicop_code, coicop_label, weight, base_price_p0)
# base_price_p0 = current Kassal price (May 2026); MoM will accumulate from here.
ADD = [
    ("7025165010827", "Coop Skåret Toastloff 750g", "kassal", "01.1.1",
     "Bread and cereals", 3.50, 36.90),
    ("7340191114173", "Änglamark Fruktmüsli 500g", "kassal", "01.1.1",
     "Bread and cereals", 1.50, 59.90),
    ("7039610004378", "Prior Hel Kylling Grillet 700g", "kassal", "01.1.2",
     "Meat", 4.50, 99.90),
    ("5601010211070", "Sardiner Naturell 125g Ramirez", "kassal", "01.1.3",
     "Fish and seafood", 1.00, 37.50),
    ("5903240405190", "Epler 1kg First Price", "kassal", "01.1.6",
     "Fruit", 2.00, 19.90),
]

# Name correction for Friele (EAN and COICOP stay the same)
RENAME = {
    "7037150127007": "Friele Frokostkaffe Mørk Filtermalt 250g",
}


async def main() -> None:
    pool = await asyncpg.create_pool(DATABASE_URL)

    # Deactivate dead products
    for ean, reason in DEACTIVATE.items():
        result = await pool.execute(
            "UPDATE products SET active = FALSE WHERE ean = $1", ean
        )
        print(f"  DEACTIVATE {ean}: {result} — {reason}")

    # Insert replacements (skip if EAN already present)
    for row in ADD:
        result = await pool.execute(
            """INSERT INTO products
                (ean, name, store_chain, coicop_code, coicop_label,
                 ssb_weight_2026, base_price_p0)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (ean) DO UPDATE SET active = TRUE, name = EXCLUDED.name
            """,
            *row,
        )
        print(f"  ADD/ACTIVATE {row[0]} '{row[1]}': {result}")

    # Fix Friele name
    for ean, new_name in RENAME.items():
        result = await pool.execute(
            "UPDATE products SET name = $1 WHERE ean = $2", new_name, ean
        )
        print(f"  RENAME {ean} -> '{new_name}': {result}")

    # Final coverage summary
    rows = await pool.fetch(
        """SELECT coicop_code, COUNT(*) as n
           FROM products WHERE active = TRUE
           GROUP BY coicop_code ORDER BY coicop_code"""
    )
    print("\nActive product counts after migration:")
    for r in rows:
        print(f"  {r['coicop_code']}: {r['n']}")

    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
