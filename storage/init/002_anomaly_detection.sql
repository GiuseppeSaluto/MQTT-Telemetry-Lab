-- Rolling z-score anomaly detection, independent of the simulator's fault label.
--
-- A function rather than a view: a time filter on a view can't reach inside
-- its window function, so every query scored the whole table. Here only
-- [from_ts - 5 min, to_ts) is read, the extra 5 min warming up the window.
--
-- Idle samples are neither scored nor part of the baseline: a stopped machine
-- is a known operating mode, not an anomaly, and its low readings would
-- inflate the stddev and hide real spikes.

DROP VIEW IF EXISTS telemetry_anomaly_scores;

CREATE OR REPLACE FUNCTION anomaly_scores(from_ts TIMESTAMPTZ, to_ts TIMESTAMPTZ)
RETURNS TABLE (
    "time"              TIMESTAMPTZ,
    line                TEXT,
    machine_id          TEXT,
    temperature_zscore  DOUBLE PRECISION,
    vibration_zscore    DOUBLE PRECISION,
    is_anomaly          BOOLEAN
)
LANGUAGE sql STABLE AS $$
    SELECT
        time, line, machine_id, temperature_zscore, vibration_zscore,
        -- a constant signal has no z-score (NULL): not an anomaly
        window_count >= 10
            AND coalesce(abs(temperature_zscore) > 3 OR abs(vibration_zscore) > 3, false)
    FROM (
        SELECT
            t.time, t.line, t.machine_id,
            count(*) OVER w AS window_count,
            CASE WHEN stddev(t.temperature) OVER w > 0
                 THEN (t.temperature - avg(t.temperature) OVER w) / stddev(t.temperature) OVER w
            END AS temperature_zscore,
            CASE WHEN stddev(t.vibration) OVER w > 0
                 THEN (t.vibration - avg(t.vibration) OVER w) / stddev(t.vibration) OVER w
            END AS vibration_zscore
        FROM telemetry t
        WHERE t.time >= from_ts - INTERVAL '5 minutes' AND t.time < to_ts
          AND t.state <> 'idle'
        WINDOW w AS (
            PARTITION BY t.machine_id
            ORDER BY t.time
            RANGE BETWEEN INTERVAL '5 minutes' PRECEDING AND CURRENT ROW
            EXCLUDE CURRENT ROW
        )
    ) scored
    WHERE time >= from_ts;
$$;
