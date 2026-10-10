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
  dashboard, plant view first, then one machine:
  - **Plant**: availability, machines in fault now, anomalous samples and
    energy for the selected range; availability by line; machines ranked by
    availability, lowest first (`machine_kpis()`, see `storage/`); a state
    timeline with one row per machine.
  - **Machine detail**: temperature, vibration, rpm, power and the two
    z-score panels for the machine picked in the `machine_id` variable, with
    annotations for detected anomalies (and simulated faults, off by default).
  Filterable by line. The variables only scan the selected time range, not
  the whole table.
- `grafana/provisioning/alerting/rules.yml`: multi-dimensional alert rule,
  one instance per machine (`machine_id` label), firing while that machine has
  an anomalous sample (`anomaly_scores().is_anomaly`, see `storage/`) in the
  last 2 minutes. A single plant-wide rule would be firing almost all the time
  with 36 machines.
