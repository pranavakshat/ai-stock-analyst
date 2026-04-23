-- ─────────────────────────────────────────────────────────────────────────────
-- AI Stock Analyst — SQLite Schema
-- ─────────────────────────────────────────────────────────────────────────────

-- Daily picks produced by each model
CREATE TABLE IF NOT EXISTS predictions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT    NOT NULL,           -- ISO date, e.g. "2025-01-15"
    model_name      TEXT    NOT NULL,           -- "claude", "chatgpt", etc.
    rank            INTEGER NOT NULL,           -- 1-5
    ticker          TEXT    NOT NULL,           -- e.g. "AAPL"
    direction       TEXT    DEFAULT 'LONG',     -- "LONG" or "SHORT"
    allocation_pct  REAL    DEFAULT 20.0,       -- portfolio % allocated to this pick (all 5 sum to 100)
    reasoning       TEXT,                       -- model's explanation
    confidence      TEXT,                       -- "High" / "Medium" / "Low"
    raw_response    TEXT,                       -- full raw API response (for debugging)
    created_at      TEXT    DEFAULT (datetime('now'))
);

-- Actual end-of-day stock prices fetched via yfinance
CREATE TABLE IF NOT EXISTS stock_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT    NOT NULL,
    ticker          TEXT    NOT NULL,
    open_price      REAL,
    close_price     REAL,
    price_change    REAL,                       -- absolute $
    price_change_pct REAL,                     -- percentage
    volume          INTEGER,
    fetched_at      TEXT    DEFAULT (datetime('now')),
    UNIQUE(date, ticker)
);

-- Per-prediction accuracy record (joined from predictions + stock_results)
CREATE TABLE IF NOT EXISTS accuracy_scores (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id   INTEGER REFERENCES predictions(id),
    model_name      TEXT    NOT NULL,
    date            TEXT    NOT NULL,
    ticker          TEXT    NOT NULL,
    predicted_rank  INTEGER,
    actual_change_pct REAL,
    is_correct      INTEGER,                    -- 1 if stock went up, 0 if down
    calculated_at   TEXT    DEFAULT (datetime('now'))
);

-- Simulated $10 000 portfolio per model, tracked daily
CREATE TABLE IF NOT EXISTS portfolio_values (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name      TEXT    NOT NULL,
    date            TEXT    NOT NULL,
    portfolio_value REAL    NOT NULL,
    daily_return    REAL,                       -- $ gain/loss that day
    daily_return_pct REAL,                     -- % gain/loss that day
    calculated_at   TEXT    DEFAULT (datetime('now')),
    UNIQUE(model_name, date)
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_predictions_date       ON predictions(date);
CREATE INDEX IF NOT EXISTS idx_predictions_model_date ON predictions(model_name, date);
CREATE INDEX IF NOT EXISTS idx_stock_results_date     ON stock_results(date);
CREATE INDEX IF NOT EXISTS idx_accuracy_model         ON accuracy_scores(model_name);
CREATE INDEX IF NOT EXISTS idx_portfolio_model        ON portfolio_values(model_name);
