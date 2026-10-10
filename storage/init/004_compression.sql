-- Native compression for chunks older than a day: columnar, one segment per
-- machine, ordered by time. Measured on 2 days of simulated data (36
-- machines, 3.1M rows): 589 MB -> 84 MB, same query results, per-machine
-- reads ~4x faster. Late rows (broker redelivery) still go through ON CONFLICT.
-- Idempotent, so it can be applied to an existing volume.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM timescaledb_information.compression_settings
                   WHERE hypertable_name = 'telemetry') THEN
        ALTER TABLE telemetry SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'line, machine_id',
            timescaledb.compress_orderby = 'time DESC'
        );
    END IF;
END $$;

SELECT add_compression_policy('telemetry', INTERVAL '1 day', if_not_exists => true);
