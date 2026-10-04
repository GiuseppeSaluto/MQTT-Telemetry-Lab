-- Per-machine availability, time in each state and energy over a time range.
-- Each sample is assumed to last until the machine's next sample.
-- Availability = running time / observed time. Not full OEE: performance and
-- quality need part counts (good/rejected), which the simulator doesn't emit.

CREATE OR REPLACE FUNCTION machine_kpis(from_ts TIMESTAMPTZ, to_ts TIMESTAMPTZ)
RETURNS TABLE (
    machine_id        TEXT,
    line              TEXT,
    availability_pct  DOUBLE PRECISION,
    running_min       DOUBLE PRECISION,
    idle_min          DOUBLE PRECISION,
    fault_min         DOUBLE PRECISION,
    energy_kwh        DOUBLE PRECISION
)
LANGUAGE sql STABLE AS $$
    WITH samples AS (
        SELECT
            t.machine_id, t.line, t.state, t.power_consumption,
            -- ponytail: a gap longer than 10 s (simulator/ingestion down) counts
            -- as 10 s in the last known state, the rest is unobserved; fine for
            -- a 2 s tick, would need a per-machine expected interval otherwise.
            LEAST(COALESCE(EXTRACT(EPOCH FROM
                lead(t.time) OVER (PARTITION BY t.machine_id ORDER BY t.time) - t.time
            ), 0), 10) AS seconds
        FROM telemetry t
        WHERE t.time >= from_ts AND t.time < to_ts
    )
    SELECT
        machine_id,
        line,
        100 * sum(seconds) FILTER (WHERE state = 'running') / NULLIF(sum(seconds), 0),
        coalesce(sum(seconds) FILTER (WHERE state = 'running'), 0) / 60,
        coalesce(sum(seconds) FILTER (WHERE state = 'idle'), 0) / 60,
        coalesce(sum(seconds) FILTER (WHERE state = 'fault'), 0) / 60,
        sum(power_consumption * seconds) / 3600  -- power_consumption is in kW
    FROM samples
    GROUP BY machine_id, line
    ORDER BY machine_id;
$$;
