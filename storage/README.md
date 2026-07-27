# Storage

TimescaleDB schema and init scripts, run automatically on first container
start via the `docker-entrypoint-initdb.d` mount (see `init/`).

TODO:
- `init/001_schema.sql`: telemetry table + `create_hypertable`
- retention policy (e.g. drop chunks older than N days)
- indexes for the query patterns the dashboard needs (per machine, per line, time range)
