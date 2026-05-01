# Norwegian CPI Nowcasting Engine

[![Daily Scraper](https://github.com/Jakobkoding2/norwegian-cpi-nowcast/actions/workflows/scrape.yml/badge.svg)](https://github.com/Jakobkoding2/norwegian-cpi-nowcast/actions/workflows/scrape.yml)
[![CI](https://github.com/Jakobkoding2/norwegian-cpi-nowcast/actions/workflows/ci.yml/badge.svg)](https://github.com/Jakobkoding2/norwegian-cpi-nowcast/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11+-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Real-time Norwegian food CPI tracker and SSB monthly print predictor. Ingests daily grocery prices from **Kassal.app**, computes a **Laspeyres price index** weighted by SSB Table 14700 basket weights, and runs an **XGBoost nowcast model** to predict Statistics Norway's monthly food CPI release — typically 10 days before it's published.

---

## How it works

```
Kassal API ──► raw_prices (Neon/TimescaleDB)
                    │
                    ▼
            Promo filter (7-day rolling median)
                    │
                    ▼
            Laspeyres index  ──► daily_index table
                    │
                    ▼
            XGBoost model + EUR/NOK + promo intensity
                    │
                    ▼
            Point estimate + 95% CI  ──► nowcast table
                    │
                    ▼
            FastAPI + Streamlit dashboard
```

---

## Stack

| Layer | Technology |
|---|---|
| Data ingestion | Python `asyncio` + `httpx`, `curl_cffi` (TLS fingerprint spoofing for fallback sources) |
| Database | PostgreSQL 16 on [Neon](https://neon.tech) (TimescaleDB-compatible schema) |
| Index engine | Pandas — Laspeyres formula, 7-day rolling median promo filter |
| Nowcast model | XGBoost Regressor, bootstrap 95% CI, trained on historical SSB prints |
| API | FastAPI — `/index`, `/nowcast/latest`, `/ssb`, `/breakdown/{date}` |
| Dashboard | Streamlit + Plotly — 3 charts (daily curve, nowcast CI band, COICOP breakdown) |
| Orchestration | GitHub Actions cron (`0 2 * * *`) — daily scrape + monthly nowcast |
| Containers | Docker Compose (TimescaleDB, scraper, API) |

---

## Project structure

```
norwegian-cpi-nowcast/
├── .github/workflows/
│   ├── scrape.yml          # Daily 02:00 UTC price scraper + indexer cron
│   └── ci.yml              # Lint (ruff), type check (mypy), tests (pytest)
├── db/
│   ├── schema.sql          # PostgreSQL schema + TimescaleDB hypertable
│   └── seed_products.py    # Seeds ~74 EANs across all 9 COICOP food groups
├── scraper/
│   ├── main.py             # Async orchestrator: Kassal → Oda → Meny fallback
│   ├── kassal.py           # Kassal.app API client (name-based search)
│   ├── oda.py              # Oda fallback (TLS-spoofed REST API)
│   └── meny.py             # Meny fallback (NGData Elasticsearch)
├── indexer/
│   ├── promo_filter.py     # 7-day rolling median, IQR outlier removal
│   ├── laspeyres.py        # Laspeyres index engine → daily_index table
│   └── run_daily.py        # CLI entry point
├── model/
│   ├── features.py         # EUR/NOK (Norges Bank API), promo intensity, volatility
│   ├── train.py            # XGBoost training with TimeSeriesSplit CV
│   └── predict.py          # Monthly nowcast → CI via bootstrap perturbation
├── api/
│   └── main.py             # FastAPI backend
├── frontend/
│   └── app.py              # Streamlit dashboard
└── docker-compose.yml
```

---

## COICOP basket coverage

The index tracks **74 products** across all SSB food sub-groups (Table 14700 weights):

| Code | Category | Example products |
|---|---|---|
| 01.1.1 | Bread & Cereals | Havregryn, Hvetemel, Wasa Knekkebrød |
| 01.1.2 | Meat | Gilde Bacon, Prior Kyllingfilet, Gilde Kokt Skinke |
| 01.1.3 | Fish & Seafood | Laks, Makrell i Tomat, Sardiner |
| 01.1.4 | Milk, Cheese & Eggs | Tine Helmelk, Tine Norvegia, Egg 12pk |
| 01.1.5 | Oils & Fats | Olivenolje, Melange Margarin, Tine Smør |
| 01.1.6 | Fruit | Epler Pink Lady, Appelsiner, Druer |
| 01.1.7 | Vegetables | Gulrot, Isbergsalat, Brokkoli, Poteter |
| 01.1.8 | Sugar & Confectionery | Sukker 1kg, Freia Melkesjokolade, Ahlgrens |
| 01.1.9 | Coffee, Tea & Condiments | Friele Kaffe, Mills Majones, Idun Sennep |

---

## Quickstart

### Prerequisites
- Python 3.11+
- PostgreSQL (or a [Neon](https://neon.tech) free-tier connection string)
- A [Kassal.app](https://kassal.app) API key (free)

### Setup

```bash
git clone https://github.com/Jakobkoding2/norwegian-cpi-nowcast.git
cd norwegian-cpi-nowcast

pip install .

cp .env.example .env
# Fill in DATABASE_URL and KASSAL_API_KEY

# Apply DB schema
psql $DATABASE_URL -f db/schema.sql

# Seed product catalog
python -m db.seed_products
```

### Run the scraper

```bash
python -m scraper.main
```

### Compute today's index

```bash
python -m indexer.run_daily
```

### Start the API + dashboard

```bash
# API
uvicorn api.main:app --reload

# Dashboard (separate terminal)
cd frontend
pip install -r requirements.txt
streamlit run app.py
```

### Docker

```bash
cp .env.example .env   # fill in credentials
docker compose up
```

---

## GitHub Actions

The scraper fires automatically at **02:00 UTC every night**. Required repository secrets:

| Secret | Description |
|---|---|
| `DATABASE_URL` | Neon / Supabase / Hetzner PostgreSQL connection string |
| `KASSAL_API_KEY` | Kassal.app API key |

The nowcast model runs on the **1st of each month** (after the scrape job completes) to predict the SSB print scheduled for the 10th.

---

## Nowcast model

Features used to predict the SSB monthly food CPI print:

- **Internal MoM %** — our daily Laspeyres index MoM change (first 3 weeks, matching SSB's collection window)
- **EUR/NOK MoM %** — from the [Norges Bank API](https://data.norges-bank.no)
- **Promo intensity ratio** — share of basket items on promotion
- **Price volatility** — mean standard deviation of price relatives across COICOP groups

The 95% confidence interval is estimated via bootstrap perturbation (1 000 rounds of ±0.3pp feature noise).

---

## Data sources

| Source | Use |
|---|---|
| [Kassal.app API](https://kassal.app/api) | Primary daily grocery prices (free tier) |
| Oda.com API | Fallback — TLS-fingerprint-spoofed REST |
| Meny / NGData | Fallback — Elasticsearch endpoint |
| [Norges Bank API](https://data.norges-bank.no) | EUR/NOK exchange rate for model features |
| SSB Table 14700 | Official basket weights + historical CPI prints |
