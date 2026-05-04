# Norwegian CPI Nowcast - Deployment Guide

## Quick Start (5 minutes)

### 1. Set Up Database

Use **Neon** (free PostgreSQL hosting):

```bash
# Create account at neon.tech
# Create project → get connection string like:
# postgresql://user:password@project.neon.tech/database

# Clone the schema
psql $DATABASE_URL -f db/schema.sql

# Seed 74 products
python -m db.seed_products

# Bootstrap SSB historical data (optional, for backtesting)
python -m db.fetch_ssb_history
```

### 2. Deploy the API

**Choose one:**

#### Render (Easiest, no credit card)
```bash
# 1. Push repo to GitHub
# 2. Go to render.com → New → Web Service
# 3. Connect Norwegian-CPI-Nowcast repo
# 4. Settings:
#    - Root directory: (blank)
#    - Build: pip install .
#    - Start: uvicorn api.main:app --host 0.0.0.0 --port $PORT
#    - Environment: DATABASE_URL=<your-neon-url>
# 5. Deploy → you get a URL like: https://norwegian-api.onrender.com
```

#### Railway
```bash
railway link (select repo)
railway variables set DATABASE_URL=<neon-url>
railway up
```

#### Fly.io (Always-on free tier)
```bash
cd api
fly launch   # follow prompts
fly secrets set DATABASE_URL="<neon-url>"
fly deploy
```

### 3. Deploy the Dashboard

```bash
# 1. Go to share.streamlit.io → New app
# 2. Repository: Jakobkoding2/norwegian-cpi-nowcast
#    Branch: master
#    Main file: frontend/app.py
# 3. Click Deploy
# 4. Once live, click "App settings" → "Secrets"
# 5. Paste:
[API_URL]
"https://your-api.onrender.com"
# 6. Dashboard redeploys automatically
```

---

## GitHub Actions Setup

### Secrets Required

Add to **Settings → Secrets and variables → Actions:**

```
DATABASE_URL          # PostgreSQL connection string
KASSAL_API_KEY        # Free from kassal.app/api
OPENROUTER_API_KEY    # (Optional) for daily-light.yml maintenance
```

### Workflows

| Workflow | Schedule | What it does |
|---|---|---|
| `ci.yml` | Every push | Lint + type check + tests |
| `scrape.yml` | Daily 02:00 UTC | Scrape prices + compute index |
| `retrain.yml` | 12th @ 06:00 UTC | Retrain model after SSB publishes |
| `daily-light.yml` | Daily 03:00 UTC | Light maintenance (optional) |

---

## Local Development

### Prerequisites
- Python 3.11+
- PostgreSQL (or Neon)

### Setup

```bash
# Clone and install
git clone https://github.com/Jakobkoding2/norwegian-cpi-nowcast.git
cd norwegian-cpi-nowcast
pip install -e ".[dev]"

# Environment variables
cp .env.example .env
# Edit .env:
# DATABASE_URL=postgresql://...
# KASSAL_API_KEY=...

# Initialize database
psql $DATABASE_URL -f db/schema.sql
python -m db.seed_products

# Run daily pipeline
python -m scraper.main           # Fetch prices
python -m indexer.run_daily      # Compute indices

# Run model training (after 12 months of data)
python -m db.export_training_data
python -m model.train
python -m model.predict
```

### Run Services Locally

**Terminal 1 — API:**
```bash
export DATABASE_URL=postgresql://...
export KASSAL_API_KEY=...
uvicorn api.main:app --reload --port 8000
```

**Terminal 2 — Dashboard:**
```bash
export API_URL=http://localhost:8000
streamlit run frontend/app.py --server.port 8501
```

Visit:
- API: http://localhost:8000/docs (interactive docs)
- Dashboard: http://localhost:8501

---

## Testing

### Run Tests
```bash
pytest tests/ -v
```

### Type Check
```bash
mypy scraper/ indexer/ model/ api/ --ignore-missing-imports
```

### Lint
```bash
ruff check .
```

---

## Troubleshooting

### Dashboard shows "server error"

1. Check if API is running:
   ```bash
   curl https://your-api-url.com/health
   ```
   Should return: `{"status":"ok"}`

2. Check Streamlit Cloud logs:
   - Go to share.streamlit.io → manage app
   - View logs for connection errors

3. Verify `API_URL` secret is set (case-sensitive):
   ```toml
   API_URL = "https://your-api.onrender.com"
   ```

### Scraper fails with "KASSAL_API_KEY not found"

1. Verify GitHub Actions secret is set
2. Check workflow file uses correct secret name
3. Test locally:
   ```bash
   export KASSAL_API_KEY=your_key
   python -m scraper.main
   ```

### Database connection errors

1. Test connection:
   ```bash
   psql $DATABASE_URL -c "SELECT 1"
   ```

2. Check connection string format:
   ```
   postgresql://user:password@host:port/dbname
   ```

3. Ensure Neon project allows your IP (if using IP whitelist)

### API times out on cold start (Render free tier)

Render free tier sleeps after 15 minutes of inactivity. First request takes ~30 seconds.

**Solution:** Upgrade to Starter plan ($7/mo) or use Fly.io (always-on free tier).

---

## Architecture Diagram

```
┌─────────────────────────────────────┐
│   GitHub Actions (Orchestration)    │
├─────────────────────────────────────┤
│                                     │
│  Daily 02:00 UTC:                   │
│  scraper.main → indexer.run_daily   │
│                ↓                    │
│  12th @ 06:00 UTC:                  │
│  model.train → model.predict        │
└────────────┬────────────────────────┘
             │
      ┌──────▼──────┐
      │  Neon DB    │
      │ PostgreSQL  │
      ├─────────────┤
      │ raw_prices  │
      │ daily_index │
      │ ssb_official│
      │ nowcast     │
      └──────┬──────┘
             │
        ┌────┴────┐
        │          │
    ┌───▼───┐  ┌──▼────┐
    │ FastAPI   │ │ Streamlit │
    │ (Render)  │ │ (Cloud)   │
    └────┬──────┘ └──────┬────┘
         │               │
         └───────┬───────┘
                 │
          ┌──────▼──────┐
          │   Users     │
          │  Dashboard  │
          └─────────────┘
```

---

## Environment Variables

### Required

- `DATABASE_URL` — PostgreSQL connection string
- `KASSAL_API_KEY` — Kassal.app API key

### Optional

- `OPENROUTER_API_KEY` — For daily-light.yml AI maintenance
- `API_URL` — Streamlit dashboard (secret, not env var)

---

## Monitoring

### Health Check

```bash
curl https://your-api.com/health
```

Expected: `{"status":"ok"}`

### Recent Nowcast

```bash
curl https://your-api.com/nowcast/latest | jq
```

Expected:
```json
{
  "run_date": "2026-05-04",
  "target_month": "2026-05-01",
  "point_estimate": 2.3,
  "ci_lower_95": 1.9,
  "ci_upper_95": 2.7,
  "xgb_version": "xgb_v1"
}
```

### Recent Index

```bash
curl 'https://your-api.com/index?from_date=2026-05-01' | jq
```

---

## Support

- **Issues:** GitHub Issues
- **Docs:** README.md
- **Status:** See .claude/SYSTEM_STATUS.md
