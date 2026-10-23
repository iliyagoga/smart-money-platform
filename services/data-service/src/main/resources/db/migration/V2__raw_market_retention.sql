-- Raw OKX trades and order-book snapshots are optional and high volume.
-- Short chunks let Timescale drop old data promptly when collection is enabled.
-- Existing chunks retain their original interval until they age out.
SELECT set_chunk_time_interval('market_ticks', INTERVAL '1 hour');
SELECT set_chunk_time_interval('order_books', INTERVAL '1 hour');
SELECT add_retention_policy('market_ticks', drop_after => INTERVAL '6 hours', schedule_interval => INTERVAL '1 hour', if_not_exists => TRUE);
SELECT add_retention_policy('order_books', drop_after => INTERVAL '2 hours', schedule_interval => INTERVAL '1 hour', if_not_exists => TRUE);
