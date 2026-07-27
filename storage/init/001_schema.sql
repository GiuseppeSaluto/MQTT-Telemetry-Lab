-- Telemetry hypertable + retention policy.
-- Executed automatically on first container start (docker-entrypoint-initdb.d).

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE telemetry (
    time               TIMESTAMPTZ NOT NULL,
    line               TEXT NOT NULL,
    machine_id         TEXT NOT NULL,
    temperature        DOUBLE PRECISION,
    vibration          DOUBLE PRECISION,
    rpm                DOUBLE PRECISION,
    power_consumption  DOUBLE PRECISION,
    state              TEXT NOT NULL CHECK (state IN ('running', 'idle', 'fault'))
);

-- Partition by time; 1 day chunks are plenty for this data volume/rate.
SELECT create_hypertable('telemetry', 'time', chunk_time_interval => INTERVAL '1 day');

-- Dashboard queries filter by machine (or line) and time range.
CREATE INDEX idx_telemetry_machine_time ON telemetry (machine_id, time DESC);
CREATE INDEX idx_telemetry_line_time ON telemetry (line, time DESC);

-- Drop data older than 30 days.
SELECT add_retention_policy('telemetry', INTERVAL '30 days');
