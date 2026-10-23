-- Read-only storage report for the PostgreSQL/TimescaleDB volume.
SELECT current_database() AS database_name,
       pg_size_pretty(pg_database_size(current_database())) AS database_size;

SELECT hypertable_name,
       pg_size_pretty(hypertable_size(format('%I.%I', hypertable_schema, hypertable_name)::regclass)) AS total_size
FROM timescaledb_information.hypertables
ORDER BY hypertable_size(format('%I.%I', hypertable_schema, hypertable_name)::regclass) DESC;

SELECT n.nspname AS schema_name, c.relname AS table_name,
       pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r','p') AND n.nspname NOT IN ('pg_catalog','information_schema','_timescaledb_internal')
ORDER BY pg_total_relation_size(c.oid) DESC LIMIT 20;

SELECT pg_size_pretty(coalesce(sum(size),0)) AS wal_size FROM pg_ls_waldir();

SELECT hypertable_name, chunk_name, range_start, range_end
FROM timescaledb_information.chunks
WHERE hypertable_name IN ('market_ticks','order_books')
ORDER BY hypertable_name, range_start DESC LIMIT 30;

SELECT hypertable_name, job_id, schedule_interval, config
FROM timescaledb_information.jobs
WHERE hypertable_name IN ('market_ticks','order_books') AND proc_name='policy_retention'
ORDER BY hypertable_name;

SELECT hypertable_name, chunk_name, pg_size_pretty(total_bytes) AS total_size
FROM (
  SELECT 'market_ticks' AS hypertable_name, chunk_name, total_bytes
  FROM chunks_detailed_size('market_ticks')
  UNION ALL
  SELECT 'order_books' AS hypertable_name, chunk_name, total_bytes
  FROM chunks_detailed_size('order_books')
) raw_chunks
ORDER BY total_bytes DESC LIMIT 20;
