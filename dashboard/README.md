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
  state timeline (running/idle/fault), a current-status table, and
  annotations that mark fault episodes on the time series panels. Filterable
  by `line`/`machine_id` template variables.
