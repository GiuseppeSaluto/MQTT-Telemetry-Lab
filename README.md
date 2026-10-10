# MQTT Telemetry Lab

[![CI](https://github.com/GiuseppeSaluto/MQTT-Telemetry-Lab/actions/workflows/ci.yml/badge.svg)](https://github.com/GiuseppeSaluto/MQTT-Telemetry-Lab/actions/workflows/ci.yml)

Industrial IoT lab: simulated machines publish telemetry over MQTT, a Rust
service ingests it into TimescaleDB, and Grafana shows live trends,
availability / downtime / energy per machine, and statistical anomaly
detection with alerting. Every piece runs as its own Docker service.

![Grafana "Factory Overview" dashboard: telemetry, machine states, KPIs and detected anomalies for a 36-machine plant, then one machine in detail](docs/images/dashboard.png)

## Architecture
```mermaid
flowchart LR
    SIM[simulator\nPython] -->|MQTT publish| MQ[Mosquitto]
    MQ -->|MQTT subscribe| ING[ingestion\nRust]
    ING -->|write| DB[(TimescaleDB)]
    DB --> GRAF[Grafana\ndashboard + alerts]
    CFG[config/machines.yaml] -.-> SIM
```

| Component | What it does |
|---|---|
| `simulator/` | 36 machines on 4 lines, read from `config/machines.yaml`. Each is a running / idle / fault state machine with drifting, noisy readings (temperature, vibration, rpm, power) and occasional fault spikes. |
| `ingestion/` | Subscribes to `factory/+/+/telemetry` and writes to TimescaleDB. At-least-once delivery: persistent MQTT session, ack only after the insert, duplicates ignored. Invalid data is logged and dropped; clean shutdown on SIGTERM. |
| `storage/` | Hypertable (1-day chunks, 30-day retention) and two SQL functions: `machine_kpis()` (availability, minutes per state, kWh) and `anomaly_scores()` (rolling z-score). |
| `dashboard/` | Grafana provisioned as code: datasource, "Factory Overview" dashboard, alert rule on detected anomalies. |

## Design choices
- **TimescaleDB**: the data is fixed-schema numeric time series queried by
  time range, so plain SQL with window functions fits, and time partitioning
  skips the chunks outside the range. The anomaly alert query reads only the
  last minutes: 3.6 ms on 30 days of data (3.9M rows), against 61 s for the
  first version, which scored the whole table.
- **Rust for ingestion**: a single small binary with no runtime, the piece
  that would sit on an edge gateway next to the machines. At this data rate
  Python would cope too, and a config-only tool such as Telegraf could replace
  it; the point here is a small consumer (an 8 MB image holding only a
  static binary, ~2 MiB of RAM with 36 machines, not running as root) that doesn't lose
  data: with the database stopped for 60 s, no sample is lost (see
  `ingestion/README.md`).
- **Anomaly detection independent of the fault label**: the z-score never
  looks at the simulator's `fault` state, it only sees the numbers. Idle
  samples are left out, since a stopped machine is a known operating mode,
  not an anomaly. The threshold is |z| > 5, not the textbook 3: on 10 hours
  of simulated data it caught all 83 faults with 0.1 false alarms per hour,
  against 42 per hour at 3, because the readings drift slowly.
- **Availability, not full OEE**: performance and quality need part counts
  (good / rejected), which the simulator doesn't produce.
- **No hardcoded config**: machines, lines and thresholds come from
  `config/machines.yaml`, credentials from `.env`.

## Scope
A lab, not a production deployment: the data is simulated, there is no real
PLC, OPC UA or fieldbus connection, and the broker runs without auth/TLS
(bound to localhost only).

## Run
```bash
cp .env.example .env   # then edit .env with your own values
docker compose up -d
```

| Service     | URL / Port              | Notes                                  |
|-------------|--------------------------|-----------------------------------------|
| Grafana     | http://localhost:3000    | Login with `GRAFANA_ADMIN_USER`/`GRAFANA_ADMIN_PASSWORD` from `.env`; dashboard "Factory Overview" |
| TimescaleDB | `localhost:5432`         | Connect with any Postgres client (e.g. DBeaver) using the `POSTGRES_*` values from `.env` |
| Mosquitto   | `localhost:1883`         | MQTT broker, topic `factory/{line}/{machine_id}/telemetry` |

To follow logs for a single service: `docker compose logs -f simulator` (or
`ingestion`, `grafana`, ...).

## Tests
CI runs clippy and the unit tests for the Rust service, ruff and pytest for
the simulator, validates the compose file, and runs the SQL self-checks in
`storage/tests/` against a fresh TimescaleDB with the init scripts applied
(see `storage/README.md`).
