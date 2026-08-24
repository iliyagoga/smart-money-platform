CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE candles (
  symbol text NOT NULL, timeframe varchar(4) NOT NULL, ts timestamptz NOT NULL,
  open numeric(30,12) NOT NULL, high numeric(30,12) NOT NULL, low numeric(30,12) NOT NULL,
  close numeric(30,12) NOT NULL, volume numeric(36,12) NOT NULL,
  quote_volume numeric(36,12), trades_count bigint, is_closed boolean NOT NULL,
  PRIMARY KEY(symbol,timeframe,ts), CHECK(high>=low), CHECK(open BETWEEN low AND high), CHECK(close BETWEEN low AND high)
);
SELECT create_hypertable('candles','ts',if_not_exists=>TRUE);
CREATE INDEX candles_lookup_idx ON candles(symbol,timeframe,ts DESC);

CREATE TABLE market_ticks (
  symbol text NOT NULL, trade_id text NOT NULL, ts timestamptz NOT NULL,
  price numeric(30,12) NOT NULL, volume numeric(36,12) NOT NULL, side varchar(4) NOT NULL CHECK(side IN ('buy','sell')),
  PRIMARY KEY(symbol,trade_id,ts)
);
SELECT create_hypertable('market_ticks','ts',if_not_exists=>TRUE);
CREATE INDEX market_ticks_lookup_idx ON market_ticks(symbol,ts DESC);

CREATE TABLE order_books (
  symbol text NOT NULL, ts timestamptz NOT NULL, sequence_id bigint NOT NULL, bids jsonb NOT NULL, asks jsonb NOT NULL,
  PRIMARY KEY(symbol,ts)
);
SELECT create_hypertable('order_books','ts',if_not_exists=>TRUE);
CREATE INDEX order_books_lookup_idx ON order_books(symbol,ts DESC);
