# Storage

TimescaleDB schema and init scripts, run automatically on first container
start via the `docker-entrypoint-initdb.d` mount (see `init/`). Init scripts
only run against an empty data volume — if you change `001_schema.sql` after
the volume already exists, drop the `timescaledb_data` volume to re-apply it.

- `init/001_schema.sql`: `telemetry` hypertable (1-day chunks), a `CHECK`
  constraint on `state` (`running`/`idle`/`fault`), indexes on
  `(machine_id, time DESC)` and `(line, time DESC)` for the dashboard's query
  patterns, and a 30-day retention policy.
