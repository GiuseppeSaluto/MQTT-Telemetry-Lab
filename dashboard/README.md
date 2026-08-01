# Dashboard

Grafana with automatic provisioning (datasource + dashboard JSON), mounted by
docker-compose into the Grafana container. Both are read-only from the UI
(`editable: false` / `allowUiUpdates: false`) so the files here stay the
single source of truth — edit the JSON/YAML, not the running Grafana.

- `grafana/provisioning/datasources/datasource.yml`: TimescaleDB (Postgres)
  datasource, credentials from env vars, fixed `uid: timescaledb` (referenced
  by the dashboard JSON — keep it stable, a random/changed uid breaks the
  dashboard's panel queries).
- `grafana/provisioning/dashboards/dashboards.yml`: dashboard provider config,
  loads any JSON dropped in `grafana/dashboards/`.
- `grafana/dashboards/factory-overview.json`: the "Factory Overview"
  dashboard — per-machine time series (temperature/vibration/rpm/power), a
  state timeline (running/idle/fault), a current-status table, z-score
  anomaly panels, and annotations for both simulated faults and detected
  anomalies. Filterable by `line`/`machine_id` template variables.
- `grafana/provisioning/alerting/rules.yml`: alert rule, fires when
  `telemetry_anomaly_scores.is_anomaly` (see `storage/`) is true in the last
  2 minutes.
