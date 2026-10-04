-- Self-check for machine_kpis(): known samples in, exact numbers out.
-- Runs in a transaction and rolls back, so it leaves no data behind.
--   docker compose exec -T timescaledb sh -c 'psql -v ON_ERROR_STOP=1 -U $POSTGRES_USER -d $POSTGRES_DB' < storage/tests/check_kpis.sql

BEGIN;

INSERT INTO telemetry (time, line, machine_id, temperature, vibration, rpm, power_consumption, state) VALUES
    ('2000-01-01 00:00:00+00', 'check_line', 'check_machine', 50, 1, 100, 36, 'running'),  -- 2 s
    ('2000-01-01 00:00:02+00', 'check_line', 'check_machine', 50, 1, 100, 36, 'running'),  -- 2 s
    ('2000-01-01 00:00:04+00', 'check_line', 'check_machine', 60, 5,   0, 72, 'fault'),    -- 2 s
    ('2000-01-01 00:00:06+00', 'check_line', 'check_machine', 30, 0,   0,  0, 'idle'),     -- 54 s gap, capped at 10 s
    ('2000-01-01 00:01:00+00', 'check_line', 'check_machine', 50, 1, 100, 36, 'running');  -- last sample, 0 s

DO $$
DECLARE k record;
BEGIN
    SELECT * INTO STRICT k FROM machine_kpis('2000-01-01', '2000-01-02');
    -- observed 16 s: running 4, fault 2, idle 10
    ASSERT k.availability_pct = 25, format('availability_pct = %s', k.availability_pct);
    ASSERT k.running_min * 60 = 4, format('running_min = %s', k.running_min);
    ASSERT k.fault_min * 60 = 2, format('fault_min = %s', k.fault_min);
    ASSERT k.idle_min * 60 = 10, format('idle_min = %s', k.idle_min);
    -- (36*2 + 36*2 + 72*2 + 0*10) kW*s / 3600 = 0.08 kWh
    ASSERT abs(k.energy_kwh - 0.08) < 1e-9, format('energy_kwh = %s', k.energy_kwh);
    RAISE NOTICE 'machine_kpis check passed';
END $$;

ROLLBACK;
