# Dashboard

Grafana with automatic provisioning (datasource + dashboard JSON), mounted by
docker-compose into the Grafana container.

TODO:
- `grafana/provisioning/datasources/`: TimescaleDB (Postgres) datasource config
- `grafana/provisioning/dashboards/`: dashboard provider config
- `grafana/dashboards/`: actual dashboard JSON (per-machine panels, anomaly markers)
