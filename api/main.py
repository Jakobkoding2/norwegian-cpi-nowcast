"""FastAPI backend — serves data to the dashboard frontend."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date

import asyncpg
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from scraper.config import settings

_pool: asyncpg.Pool | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    _pool = await asyncpg.create_pool(settings.database_url)
    yield
    if _pool:
        await _pool.close()


app = FastAPI(title="Norwegian CPI Nowcast API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def db() -> asyncpg.Pool:
    if _pool is None:
        raise HTTPException(503, "Database not ready")
    return _pool


# ── Response schemas ──────────────────────────────────────────────────────────

class DailyIndexPoint(BaseModel):
    price_date: date
    coicop_code: str
    index_value: float
    mom_pct: float | None


class NowcastResponse(BaseModel):
    run_date: date
    target_month: date
    point_estimate: float
    ci_lower_95: float
    ci_upper_95: float
    xgb_version: str | None = None


class SSBPoint(BaseModel):
    reference_month: date
    mom_pct: float
    yoy_pct: float | None


class CoicopBreakdown(BaseModel):
    coicop_code: str
    index_value: float
    mom_pct: float | None
    n_products: int | None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/index", response_model=list[DailyIndexPoint])
async def get_daily_index(
    coicop_code: str | None = Query(None),
    from_date: date = Query(default=date(2026, 1, 1)),
    to_date: date = Query(default_factory=date.today),
):
    where = "WHERE price_date BETWEEN $1 AND $2"
    params: list = [from_date, to_date]
    if coicop_code:
        where += " AND coicop_code = $3"
        params.append(coicop_code)
    rows = await db().fetch(
        f"SELECT price_date, coicop_code, index_value, mom_pct FROM daily_index {where} ORDER BY price_date DESC",
        *params,
    )
    return [dict(r) for r in rows]


@app.get("/nowcast/latest", response_model=NowcastResponse)
async def get_latest_nowcast():
    row = await db().fetchrow(
        "SELECT run_date, target_month, point_estimate, ci_lower_95, ci_upper_95,"
        " model_version AS xgb_version FROM nowcast ORDER BY run_date DESC LIMIT 1"
    )
    if not row:
        raise HTTPException(404, "No nowcast available yet")
    return dict(row)


@app.get("/ssb", response_model=list[SSBPoint])
async def get_ssb_history(
    from_date: date = Query(default=date(2024, 1, 1)),
):
    rows = await db().fetch(
        "SELECT reference_month, mom_pct, yoy_pct FROM ssb_official WHERE reference_month >= $1 ORDER BY reference_month",
        from_date,
    )
    return [dict(r) for r in rows]


@app.get("/breakdown/{price_date}", response_model=list[CoicopBreakdown])
async def get_coicop_breakdown(price_date: date):
    rows = await db().fetch(
        "SELECT coicop_code, index_value, mom_pct, n_products FROM daily_index WHERE price_date = $1 ORDER BY coicop_code",
        price_date,
    )
    if not rows:
        raise HTTPException(404, f"No index data for {price_date}")
    return [dict(r) for r in rows]


@app.get("/health")
async def health():
    await db().fetchval("SELECT 1")
    return {"status": "ok"}
