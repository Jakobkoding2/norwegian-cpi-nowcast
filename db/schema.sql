-- Enable TimescaleDB extension (no-op if using standard Postgres)
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Product catalog with COICOP mapping and SSB basket weights
CREATE TABLE IF NOT EXISTS products (
    ean             VARCHAR(20)     PRIMARY KEY,
    name            VARCHAR(255)    NOT NULL,
    store_chain     VARCHAR(50)     NOT NULL,   -- 'kassal', 'oda', 'meny', 'kiwi'
    coicop_code     VARCHAR(10)     NOT NULL,   -- e.g. '01.1.1'
    coicop_label    VARCHAR(100),
    ssb_weight_2026 DECIMAL(8,4)   NOT NULL,   -- normalised so all weights sum to 100
    base_price_p0   DECIMAL(10,2)  NOT NULL,   -- reference price (Jan 2026 baseline)
    active          BOOLEAN        DEFAULT TRUE,
    created_at      TIMESTAMPTZ    DEFAULT NOW()
);

-- Raw daily prices fetched from retailers
CREATE TABLE IF NOT EXISTS raw_prices (
    id          BIGSERIAL       PRIMARY KEY,
    ean         VARCHAR(20)     REFERENCES products(ean) ON DELETE CASCADE,
    fetched_at  TIMESTAMPTZ     DEFAULT NOW(),
    price_date  DATE            NOT NULL,
    price       DECIMAL(10,2)   NOT NULL,
    is_promo    BOOLEAN         DEFAULT FALSE,
    promo_price DECIMAL(10,2),
    source      VARCHAR(30)     NOT NULL,       -- 'kassal', 'oda_api', 'meny_api'
    UNIQUE (ean, price_date, source)            -- idempotent daily inserts
);

-- Convert to TimescaleDB hypertable for efficient time-range queries
SELECT create_hypertable('raw_prices', 'fetched_at', if_not_exists => TRUE);

-- Computed daily index values written by the indexer job
CREATE TABLE IF NOT EXISTS daily_index (
    price_date      DATE            NOT NULL,
    coicop_code     VARCHAR(10)     NOT NULL,
    index_value     DECIMAL(12,6)   NOT NULL,   -- Laspeyres index (base = 100)
    mom_pct         DECIMAL(8,4),               -- month-over-month % change
    raw_volatility  DECIMAL(10,6),              -- std-dev of underlying price relatives
    n_products      INTEGER,                    -- number of active products in basket
    PRIMARY KEY (price_date, coicop_code)
);

-- Monthly nowcast outputs from the ML model
CREATE TABLE IF NOT EXISTS nowcast (
    run_date        DATE            PRIMARY KEY,
    target_month    DATE            NOT NULL,   -- first day of the month being predicted
    point_estimate  DECIMAL(8,4)    NOT NULL,   -- predicted MoM % change
    ci_lower_95     DECIMAL(8,4)    NOT NULL,
    ci_upper_95     DECIMAL(8,4)    NOT NULL,
    model_version   VARCHAR(50),
    features_json   JSONB
);

-- Historical SSB official releases (populated manually or via SSB API)
CREATE TABLE IF NOT EXISTS ssb_official (
    reference_month DATE            PRIMARY KEY,
    mom_pct         DECIMAL(8,4)    NOT NULL,   -- official MoM food CPI %
    yoy_pct         DECIMAL(8,4),
    published_at    DATE            NOT NULL
);

-- Useful indexes
CREATE INDEX IF NOT EXISTS idx_raw_prices_ean_date ON raw_prices (ean, price_date DESC);
CREATE INDEX IF NOT EXISTS idx_daily_index_date ON daily_index (price_date DESC);
