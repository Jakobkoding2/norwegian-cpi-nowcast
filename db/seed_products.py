"""Seed the products table with 74 representative Norwegian grocery EANs.

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

EANs are the real Kassal.app identifiers discovered during first scrape run.
Base prices (base_price_p0) reflect January 2026 observed prices.

Usage:
    python -m db.seed_products
"""
# ruff: noqa: E501
from __future__ import annotations

import asyncio
import os

import asyncpg

DATABASE_URL = os.environ["DATABASE_URL"]

# fmt: off
PRODUCTS = [
    # (ean, name, store_chain, coicop_code, coicop_label, ssb_weight_2026, base_price_p0)

    # ── Bread & Cereals (01.1.1) — weight ~18% ─────────────────────────────────
    ("7025110111357", "Anglamark Hvetemel 1kg",           "kassal", "01.1.1", "Bread and cereals", 2.00, 26.90),
    ("7044416013141", "Bjorn Havregryn Lettkokte 1.1kg",  "kassal", "01.1.1", "Bread and cereals", 2.50, 29.90),
    ("7035620054948", "Hatting Loff 750g",                "kassal", "01.1.1", "Bread and cereals", 3.50, 32.90),
    ("7622210951106", "Kjeldsberg Havreflak 750g",        "kassal", "01.1.1", "Bread and cereals", 1.50, 34.90),
    ("7038010013993", "Møllens Mel 1kg",                  "kassal", "01.1.1", "Bread and cereals", 1.40, 21.90),
    ("9800001197232", "Pasta Rigatoni 500g",              "kassal", "01.1.1", "Bread and cereals", 1.20, 24.90),
    ("7048840000222", "Rema Grovbrød 750g",               "kassal", "01.1.1", "Bread and cereals", 3.20, 28.90),
    ("7072620000589", "Ris Basmati 1kg",                  "kassal", "01.1.1", "Bread and cereals", 1.40, 35.90),
    ("7300400114752", "Wasa Knekkebrød 275g",             "kassal", "01.1.1", "Bread and cereals", 1.80, 24.90),

    # ── Meat (01.1.2) — weight ~24% ────────────────────────────────────────────
    ("7025110200617", "Coop Kyllingfilet skivet 700g",    "kassal", "01.1.2", "Meat",              3.00, 132.90),
    ("7037204303265", "Gilde Bacon 150g",                 "kassal", "01.1.2", "Meat",              2.50,  49.90),
    ("7037206100022", "Gilde Kokt Skinke 110g",           "kassal", "01.1.2", "Meat",              2.00,  39.90),
    ("7033085000894", "Gilde Pølser 600g",                "kassal", "01.1.2", "Meat",              3.00,  49.90),
    ("7037203636074", "Gilde Stjernebacon skivet 120g",   "kassal", "01.1.2", "Meat",              2.00,  34.90),
    ("7037203633820", "Nortura Bacon skivet 360g",        "kassal", "01.1.2", "Meat",              2.50,  94.90),
    ("7033085017045", "Nortura Kjøttdeig 400g",           "kassal", "01.1.2", "Meat",              5.00,  54.90),
    ("7033085041699", "Nortura Kyllingfilet 700g",        "kassal", "01.1.2", "Meat",              4.50,  89.90),
    ("7033085032826", "Nortura Lammekjøtt 400g",          "kassal", "01.1.2", "Meat",              1.50,  89.90),
    ("7033085023718", "Nortura Svinekam 1kg",             "kassal", "01.1.2", "Meat",              3.50,  79.90),
    ("7039610001353", "Prior Kyllingfilet Naturell 110g", "kassal", "01.1.2", "Meat",              1.50,  37.90),

    # ── Fish & Seafood (01.1.3) — weight ~10% ──────────────────────────────────
    ("7311040802001", "Abba Sardiner 125g",               "kassal", "01.1.3", "Fish and seafood",  1.00, 24.90),
    ("7035620087509", "First Price Laksefilet 4x125g",    "kassal", "01.1.3", "Fish and seafood",  2.00, 93.90),
    ("7035620006654", "Fiskemannen Torskfilet 500g",      "kassal", "01.1.3", "Fish and seafood",  1.50, 109.00),
    ("7020049000043", "Fjordland Laks 400g",              "kassal", "01.1.3", "Fish and seafood",  2.50, 79.90),
    ("7027110222453", "King Oscar Sardiner Olivenolje",   "kassal", "01.1.3", "Fish and seafood",  1.00, 29.90),
    ("7055330008373", "Meny Reker i Majones 200g",        "kassal", "01.1.3", "Fish and seafood",  1.00, 54.90),
    ("7048840027892", "Rema Torskfilet 500g",             "kassal", "01.1.3", "Fish and seafood",  2.00, 69.90),
    ("7039010149020", "Stabburet Makrell 170g",           "kassal", "01.1.3", "Fish and seafood",  1.20, 39.90),
    ("7039010016322", "Stabburet Makrell i Tomat 110g",   "kassal", "01.1.3", "Fish and seafood",  1.20, 29.90),
    ("7048840025720", "Tine Reker 150g",                  "kassal", "01.1.3", "Fish and seafood",  1.00, 59.90),

    # ── Milk, Cheese & Eggs (01.1.4) — weight ~16% ─────────────────────────────
    ("7025110179111", "Coop Frokostegg L 12pk",           "kassal", "01.1.4", "Milk, cheese and eggs", 3.00,  46.90),
    ("7048840010429", "Prior Egg 12pk",                   "kassal", "01.1.4", "Milk, cheese and eggs", 3.50,  59.90),
    ("7048840010412", "Q-meieriene Yoghurt 500g",         "kassal", "01.1.4", "Milk, cheese and eggs", 2.00,  34.90),
    ("7038010043895", "Tine Cottage Cheese 250g",         "kassal", "01.1.4", "Milk, cheese and eggs", 1.50,  21.90),
    ("7038010000065", "Tine Helmelk 1L",                  "kassal", "01.1.4", "Milk, cheese and eggs", 4.00,  26.90),
    ("2002436900006", "Tine Jarlsberg 500g",              "kassal", "01.1.4", "Milk, cheese and eggs", 2.00, 116.22),
    ("7038010001833", "Tine Lettmelk 1L",                 "kassal", "01.1.4", "Milk, cheese and eggs", 3.50,  26.50),
    ("7038010021718", "Tine Norvegia 500g",               "kassal", "01.1.4", "Milk, cheese and eggs", 3.00, 119.00),
    ("7038010010187", "Tine Smør 500g",                   "kassal", "01.1.4", "Milk, cheese and eggs", 2.00,  72.90),
    ("7038010040436", "Tine Yoghurt Naturell Laktosefri", "kassal", "01.1.4", "Milk, cheese and eggs", 1.50,  24.90),

    # ── Oils & Fats (01.1.5) — weight ~3% ──────────────────────────────────────
    ("7035620049439", "Eldorado Solsikkeolje 1L",         "kassal", "01.1.5", "Oils and fats",     1.00, 45.90),
    ("7036110009698", "Melange Margarin 500g",            "kassal", "01.1.5", "Oils and fats",     1.50, 37.90),
    ("7048840016568", "Rema Olivenolje 750ml",            "kassal", "01.1.5", "Oils and fats",     0.80, 79.90),
    ("7048840010986", "Sunniva Margarin 400g",            "kassal", "01.1.5", "Oils and fats",     1.20, 34.90),
    ("8410086316070", "Ybarra Raps/Olivenolje 750ml",     "kassal", "01.1.5", "Oils and fats",     1.20, 95.90),

    # ── Fruit (01.1.6) — weight ~6% ─────────────────────────────────────────────
    ("2000401300004", "Appelsiner Navel",                 "kassal", "01.1.6", "Fruit",             1.50, 49.90),
    ("2000000000022", "Banan Kg",                         "kassal", "01.1.6", "Fruit",             2.50, 19.90),
    ("7039281545026", "Druer Kg",                         "kassal", "01.1.6", "Fruit",             1.00, 49.90),
    ("2000000000015", "Eple Kg",                          "kassal", "01.1.6", "Fruit",             2.00, 28.90),
    ("2615760009002", "Epler Pink Lady 6pk",              "kassal", "01.1.6", "Fruit",             2.00, 59.90),

    # ── Vegetables (01.1.7) — weight ~7% ────────────────────────────────────────
    ("4349",          "Brokkoli stykk",                   "kassal", "01.1.7", "Vegetables",        1.20, 27.90),
    ("7048840007702", "Eisberg Salat 400g",               "kassal", "01.1.7", "Vegetables",        1.00, 24.90),
    ("7040513000022", "Gulrot 750g Beger",                "kassal", "01.1.7", "Vegetables",        2.00, 32.90),
    ("2000000000084", "Gulrøtter 750g",                   "kassal", "01.1.7", "Vegetables",        1.50, 22.90),
    ("7031540001502", "Isbergsalat stykk",                "kassal", "01.1.7", "Vegetables",        1.50, 29.90),
    ("2000512500003", "Løk Kg",                           "kassal", "01.1.7", "Vegetables",        1.00, 19.90),
    ("94088",         "Paprika Rød Kg",                   "kassal", "01.1.7", "Vegetables",        1.00, 35.80),
    ("7023026411271", "Poteter 1kg",                      "kassal", "01.1.7", "Vegetables",        2.50, 41.93),
    # Tomater Kg (EAN 8002207230015) deactivated — Kassal returns a unit-price error (315.90 NOK/kg)

    # ── Sugar, chocolate, confectionery (01.1.8) — weight ~8% ───────────────────
    ("7310350132546", "Ahlgrens Bilar 130g",              "kassal", "01.1.8", "Sugar and confectionery", 0.80, 29.90),
    ("6414000020021", "Dansukker Sukker Finkornet 1kg",   "kassal", "01.1.8", "Sugar and confectionery", 1.50, 39.90),
    ("7311041000359", "Eldorado Sukker 1kg",              "kassal", "01.1.8", "Sugar and confectionery", 2.00, 39.90),
    ("7040110569908", "Freia Melkesjokolade 200g",        "kassal", "01.1.8", "Sugar and confectionery", 2.50, 62.90),
    ("7048840001458", "Rema Syltetøy Jordbær 400g",       "kassal", "01.1.8", "Sugar and confectionery", 1.00, 29.90),
    ("7040510605285", "Strøsukker 1kg",                   "kassal", "01.1.8", "Sugar and confectionery", 1.50, 19.90),

    # ── Coffee, tea, condiments (01.1.9) — weight ~8% ───────────────────────────
    ("7037150127007", "Friele Frokostkaffe Mørk 250g",    "kassal", "01.1.9", "Food n.e.c.",       2.00,  58.90),
    ("7037150151019", "Friele Kaffe 500g",                "kassal", "01.1.9", "Food n.e.c.",       3.00, 107.90),
    ("87157239",      "Heinz Ketchup 570g",               "kassal", "01.1.9", "Food n.e.c.",       1.50,  36.90),
    ("7039010524773", "Idun Sennep 265g",                 "kassal", "01.1.9", "Food n.e.c.",       0.80,  35.90),
    ("7039010081047", "Idun Sennep Grov 275g",            "kassal", "01.1.9", "Food n.e.c.",       1.00,  19.53),
    ("7048840010108", "Lipton Green Tea 20pk",            "kassal", "01.1.9", "Food n.e.c.",       0.80,  34.90),
    ("7036110006086", "Mills Majones Ekte 330g",          "kassal", "01.1.9", "Food n.e.c.",       1.50,  45.90),
    ("7048840000857", "Rema Majones 720ml",               "kassal", "01.1.9", "Food n.e.c.",       1.20,  44.90),
]
# fmt: on


async def seed() -> None:
    pool = await asyncpg.create_pool(DATABASE_URL)
    inserted = skipped = 0
    for row in PRODUCTS:
        result = await pool.execute(
            """
            INSERT INTO products (ean, name, store_chain, coicop_code, coicop_label, ssb_weight_2026, base_price_p0)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (ean) DO NOTHING
            """,
            *row,
        )
        if result == "INSERT 0 1":
            inserted += 1
        else:
            skipped += 1
    await pool.close()
    print(f"Seeded {inserted} products ({skipped} already present).")


if __name__ == "__main__":
    asyncio.run(seed())
