# Spec — MQTT Telemetry Lab

> Full reference: `docs/spec_source.pdf`.

## Goal
Industrial IoT demo: machine simulation, MQTT ingestion, time-series storage,
dashboard, anomaly detection. Portfolio project for Industry 4.0 roles.

## Components
1. `simulator/` — Python multi-machine simulator (MQTT publisher)
2. `ingestion/` — Rust MQTT subscriber -> TimescaleDB
3. `storage/` — TimescaleDB schema/init + rolling z-score anomaly detection
4. `dashboard/` — Grafana provisioning (datasource + dashboards + alerting)
5. `config/` — machines.yaml (machines, lines, thresholds) + mosquitto.conf

## Constraints
- No monolithic script: separate Docker services orchestrated via docker-compose
- No single machine: multiple machines across multiple lines
- No hardcoded config: read dynamically from `config/machines.yaml`

## Stated limits
Demo project, not real industrial IoT experience (hardware, industrial
networks, security certifications). To be presented as such in interviews.

## Status
- [x] docker-compose.yml (mosquitto, timescaledb, grafana)
- [x] simulator: data generation with drift + noise + anomalies
- [x] config/machines.yaml + config/mosquitto.conf
- [x] ingestion (Rust): MQTT subscriber -> TimescaleDB
- [x] storage: schema + retention policy
- [x] dashboard: Grafana provisioning
- [x] anomaly detection: rolling z-score view + Grafana alert rule
- [x] README with architecture diagram
