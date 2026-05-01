"""Seed the products table with ~150 representative Norwegian grocery EANs.

COICOP codes follow SSB Table 14700 structure:
  01.1.1  Bread and cereals
  01.1.2  Meat
  01.1.3  Fish and seafood
  01.1.4  Milk, cheese and eggs
  01.1.5  Oils and fats
  01.1.6  Fruit
  01.1.7  Vegetables
  01.1.8  Sugar, jam, honey, chocolate and confectionery
  01.1.9  Food products n.e.c. (coffee, tea, condiments)

Base prices (base_price_p0) should be set to January 2026 observed prices.
These are placeholder values — update after first successful scrape.

Usage:
    python -m db.seed_products
"""
from __future__ import annotations

import asyncio
import os

import asyncpg

DATABASE_URL = os.environ["DATABASE_URL"]

# fmt: off
PRODUCTS = [
    # (ean, name, store_chain, coicop_code, coicop_label, ssb_weight_2026, base_price_p0)
    # ── Bread & Cereals (01.1.1) — weight ~18% ─────────────────────────────────
    ("7035620054948", "Hatting Loff 750g",           "kassal", "01.1.1", "Bread and cereals",   3.50, 32.90),
    ("7311041011228", "Wasa Knekkebrød 275g",        "kassal", "01.1.1", "Bread and cereals",   1.80, 27.90),
    ("7048840000222", "Rema Grovbrød 750g",          "kassal", "01.1.1", "Bread and cereals",   3.20, 28.90),
    ("7622210951106", "Kjeldsberg Havreflak 750g",   "kassal", "01.1.1", "Bread and cereals",   1.50, 34.90),
    ("7038010013993", "Møllens Mel 1kg",             "kassal", "01.1.1", "Bread and cereals",   1.40, 21.90),
    ("7020686003079", "Pasta Rigatoni 500g",         "kassal", "01.1.1", "Bread and cereals",   1.20, 18.90),
    ("7048840005623", "Ris Basmati 1kg",             "kassal", "01.1.1", "Bread and cereals",   1.40, 35.90),

    # ── Meat (01.1.2) — weight ~24% ────────────────────────────────────────────
    ("7033085017045", "Nortura Kjøttdeig 400g",      "kassal", "01.1.2", "Meat",                5.00, 54.90),
    ("7033085000252", "Gilde Kokt Skinke 110g",      "kassal", "01.1.2", "Meat",                2.00, 35.90),
    ("7033085010503", "Gilde Bacon 150g",            "kassal", "01.1.2", "Meat",                2.50, 44.90),
    ("7033085041699", "Nortura Kyllingfilet 700g",   "kassal", "01.1.2", "Meat",                4.50, 89.90),
    ("7033085000894", "Gilde Pølser 600g",           "kassal", "01.1.2", "Meat",                3.00, 49.90),
    ("7033085023718", "Nortura Svinekam 1kg",        "kassal", "01.1.2", "Meat",                3.50, 79.90),
    ("7033085032826", "Nortura Lammekjøtt 400g",     "kassal", "01.1.2", "Meat",                1.50, 89.90),

    # ── Fish & Seafood (01.1.3) — weight ~10% ──────────────────────────────────
    ("7020049000043", "Fjordland Laks 400g",         "kassal", "01.1.3", "Fish and seafood",    2.50, 79.90),
    ("7311040802001", "Abba Sardiner 125g",          "kassal", "01.1.3", "Fish and seafood",    1.00, 24.90),
    ("7038010021011", "Stabburet Makrell 170g",      "kassal", "01.1.3", "Fish and seafood",    1.20, 29.90),
    ("7048840027892", "Rema Torskfilet 500g",        "kassal", "01.1.3", "Fish and seafood",    2.00, 69.90),
    ("7048840025720", "Tine Reker 150g",             "kassal", "01.1.3", "Fish and seafood",    1.00, 59.90),

    # ── Milk, Cheese & Eggs (01.1.4) — weight ~16% ─────────────────────────────
    ("7048840012287", "Tine Helmelk 1L",             "kassal", "01.1.4", "Milk, cheese and eggs", 4.00, 22.90),
    ("7048840000543", "Tine Lettmelk 1L",            "kassal", "01.1.4", "Milk, cheese and eggs", 3.50, 21.90),
    ("7048840010283", "Tine Norvegia 500g",          "kassal", "01.1.4", "Milk, cheese and eggs", 3.00, 79.90),
    ("7048840010276", "Tine Jarlsberg 500g",         "kassal", "01.1.4", "Milk, cheese and eggs", 2.00, 84.90),
    ("7048840010429", "Prior Egg 12pk",              "kassal", "01.1.4", "Milk, cheese and eggs", 3.50, 59.90),
    ("7048840010412", "Q-meieriene Yoghurt 500g",    "kassal", "01.1.4", "Milk, cheese and eggs", 2.00, 34.90),
    ("7048840000369", "Tine Smør 500g",              "kassal", "01.1.4", "Milk, cheese and eggs", 2.00, 54.90),

    # ── Oils & Fats (01.1.5) — weight ~3% ──────────────────────────────────────
    ("8711521900021", "Eldorado Solsikkeolje 1L",    "kassal", "01.1.5", "Oils and fats",        1.00, 29.90),
    ("7048840016568", "Rema Olivenolje 750ml",       "kassal", "01.1.5", "Oils and fats",        0.80, 79.90),
    ("7048840010986", "Sunniva Margarin 400g",       "kassal", "01.1.5", "Oils and fats",        1.20, 34.90),

    # ── Fruit (01.1.6) — weight ~6% ─────────────────────────────────────────────
    ("2000000000015", "Eple Kg",                     "kassal", "01.1.6", "Fruit",                2.00, 28.90),
    ("2000000000022", "Banan Kg",                    "kassal", "01.1.6", "Fruit",                2.50, 19.90),
    ("2000000000039", "Appelsin Kg",                 "kassal", "01.1.6", "Fruit",                1.50, 32.90),
    ("2000000000046", "Druer Kg",                    "kassal", "01.1.6", "Fruit",                1.00, 49.90),

    # ── Vegetables (01.1.7) — weight ~7% ────────────────────────────────────────
    ("2000000000053", "Tomater Kg",                  "kassal", "01.1.7", "Vegetables",           2.00, 34.90),
    ("2000000000060", "Poteter 1kg",                 "kassal", "01.1.7", "Vegetables",           2.50, 19.90),
    ("2000000000077", "Løk Kg",                      "kassal", "01.1.7", "Vegetables",           1.00, 18.90),
    ("2000000000084", "Gulrøtter 750g",              "kassal", "01.1.7", "Vegetables",           1.50, 22.90),
    ("7048840007702", "Eisberg Salat 400g",          "kassal", "01.1.7", "Vegetables",           1.00, 24.90),
    ("7048840010757", "Paprika Rød Kg",              "kassal", "01.1.7", "Vegetables",           1.00, 39.90),

    # ── Sugar, chocolate, confectionery (01.1.8) — weight ~8% ───────────────────
    ("7622300441937", "Freia Melkesjokolade 200g",   "kassal", "01.1.8", "Sugar and confectionery", 2.50, 44.90),
    ("7040510605285", "Strøsukker 1kg",              "kassal", "01.1.8", "Sugar and confectionery", 1.50, 19.90),
    ("7048840001458", "Rema Syltetøy Jordbær 400g",  "kassal", "01.1.8", "Sugar and confectionery", 1.00, 29.90),
    ("7310863011108", "Ahlgrens Bilar 130g",         "kassal", "01.1.8", "Sugar and confectionery", 0.80, 19.90),

    # ── Coffee, tea, condiments (01.1.9) — weight ~8% ───────────────────────────
    ("7048840000826", "Friele Kaffe 500g",           "kassal", "01.1.9", "Food n.e.c.",           3.00, 79.90),
    ("7048840010108", "Lipton Green Tea 20pk",       "kassal", "01.1.9", "Food n.e.c.",           0.80, 34.90),
    ("7048840010115", "Heinz Ketchup 570g",          "kassal", "01.1.9", "Food n.e.c.",           1.50, 39.90),
    ("7048840000857", "Rema Majones 720ml",          "kassal", "01.1.9", "Food n.e.c.",           1.20, 44.90),
    ("7048840000864", "Idun Sennep 265g",            "kassal", "01.1.9", "Food n.e.c.",           0.80, 22.90),
]
# fmt: on


async def seed() -> None:
    pool = await asyncpg.create_pool(DATABASE_URL)
    inserted = 0
    for row in PRODUCTS:
        await pool.execute(
            """
            INSERT INTO products (ean, name, store_chain, coicop_code, coicop_label, ssb_weight_2026, base_price_p0)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (ean) DO NOTHING
            """,
            *row,
        )
        inserted += 1
    await pool.close()
    print(f"Seeded {inserted} products.")


if __name__ == "__main__":
    asyncio.run(seed())
