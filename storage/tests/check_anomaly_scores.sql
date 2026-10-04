-- Self-check for anomaly_scores(): a stable baseline, then idle, recovery and
-- a spike. Runs in a transaction and rolls back, so it leaves no data behind.
--   docker compose exec -T timescaledb sh -c 'psql -v ON_ERROR_STOP=1 -U $POSTGRES_USER -d $POSTGRES_DB' < storage/tests/check_anomaly_scores.sql

BEGIN;

-- 20 running samples every 2 s, temperature alternating 50/51 (mean 50.5, stddev ~0.5)
INSERT INTO telemetry (time, line, machine_id, temperature, vibration, rpm, power_consumption, state)
SELECT '2000-01-01 00:00:00+00'::timestamptz + n * INTERVAL '2 seconds', 'check_line', 'check_machine',
       50 + n % 2, 1, 100, 10, 'running'
FROM generate_series(0, 19) n;

INSERT INTO telemetry (time, line, machine_id, temperature, vibration, rpm, power_consumption, state) VALUES
    ('2000-01-01 00:00:40+00', 'check_line', 'check_machine', 25, 0, 0, 1, 'idle'),       -- stopped: ignored
    ('2000-01-01 00:00:42+00', 'check_line', 'check_machine', 50.5, 1, 100, 10, 'running'), -- back to normal
    ('2000-01-01 00:00:44+00', 'check_line', 'check_machine', 60, 1, 0, 12, 'fault');     -- spike

DO $$
BEGIN
    ASSERT NOT EXISTS (SELECT 1 FROM anomaly_scores('2000-01-01', '2000-01-02') WHERE time = '2000-01-01 00:00:40+00'),
        'idle sample must not be scored';
    -- IS FALSE, not NOT: NULL must fail too (vibration is constant here, so its z-score is NULL)
    ASSERT (SELECT is_anomaly FROM anomaly_scores('2000-01-01', '2000-01-02') WHERE time = '2000-01-01 00:00:42+00') IS FALSE,
        'normal sample after idle must have is_anomaly = false';
    ASSERT (SELECT is_anomaly FROM anomaly_scores('2000-01-01', '2000-01-02') WHERE time = '2000-01-01 00:00:44+00'),
        'spike not flagged';
    -- a range starting at the spike must still see the 5 min before it
    ASSERT (SELECT is_anomaly FROM anomaly_scores('2000-01-01 00:00:44+00', '2000-01-02')),
        'spike not flagged when the range starts at it (window not warmed up)';
    RAISE NOTICE 'anomaly_scores check passed';
END $$;

ROLLBACK;
