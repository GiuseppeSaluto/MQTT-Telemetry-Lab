-- Rolling z-score anomaly detection, independent of the simulator's `state`.

CREATE OR REPLACE VIEW telemetry_anomaly_scores AS
SELECT
    time,
    line,
    machine_id,
    temperature,
    vibration,
    rpm,
    power_consumption,
    state,
    window_count,
    temperature_zscore,
    vibration_zscore,
    window_count >= 10
        AND (abs(temperature_zscore) > 3 OR abs(vibration_zscore) > 3) AS is_anomaly
FROM (
    SELECT
        time, line, machine_id, temperature, vibration, rpm, power_consumption, state,
        count(*) OVER w AS window_count,
        CASE WHEN stddev(temperature) OVER w > 0
             THEN (temperature - avg(temperature) OVER w) / stddev(temperature) OVER w
        END AS temperature_zscore,
        CASE WHEN stddev(vibration) OVER w > 0
             THEN (vibration - avg(vibration) OVER w) / stddev(vibration) OVER w
        END AS vibration_zscore
    FROM telemetry
    WINDOW w AS (
        PARTITION BY machine_id
        ORDER BY time
        RANGE BETWEEN INTERVAL '5 minutes' PRECEDING AND CURRENT ROW
        EXCLUDE CURRENT ROW
    )
) scored;
