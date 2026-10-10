-- Self-check for compression: KPIs are identical before and after compressing
-- a chunk, and ON CONFLICT DO NOTHING still drops a redelivered row in it.
-- Runs in a transaction and rolls back, so it leaves no data behind.
--   docker compose exec -T timescaledb sh -c 'psql -v ON_ERROR_STOP=1 -U $POSTGRES_USER -d $POSTGRES_DB' < storage/tests/check_compression.sql

BEGIN;

INSERT INTO telemetry (time, line, machine_id, temperature, vibration, rpm, power_consumption, state)
SELECT '2000-01-01 00:00:00+00'::timestamptz + n * INTERVAL '2 seconds', 'check_line', 'check_machine',
       50 + n % 3, 1 + n % 2, 100, 10 + n % 5, (ARRAY['running', 'running', 'idle', 'fault'])[1 + n % 4]
FROM generate_series(0, 99) n;

CREATE TEMP TABLE kpis_before AS SELECT * FROM machine_kpis('2000-01-01', '2000-01-02');

SELECT count(compress_chunk(c)) FROM show_chunks('telemetry', older_than => '2000-01-02'::timestamptz) c;

DO $$
BEGIN
    ASSERT (SELECT count(*) FROM timescaledb_information.chunks
            WHERE hypertable_name = 'telemetry' AND range_end <= '2000-01-02' AND is_compressed) = 1,
        'check chunk was not compressed';
    ASSERT NOT EXISTS (SELECT * FROM kpis_before EXCEPT SELECT * FROM machine_kpis('2000-01-01', '2000-01-02')),
        'machine_kpis differs after compression';
END $$;

-- redelivered row into the compressed chunk
INSERT INTO telemetry (time, line, machine_id, temperature, vibration, rpm, power_consumption, state)
VALUES ('2000-01-01 00:00:00+00', 'check_line', 'check_machine', 50, 1, 100, 10, 'running')
ON CONFLICT DO NOTHING;

DO $$
BEGIN
    ASSERT (SELECT count(*) FROM telemetry WHERE machine_id = 'check_machine'
            AND time = '2000-01-01 00:00:00+00') = 1,
        'redelivered row stored twice in a compressed chunk';
    RAISE NOTICE 'compression check passed';
END $$;

ROLLBACK;
