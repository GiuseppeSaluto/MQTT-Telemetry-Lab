# Storage

TimescaleDB schema and init scripts, run automatically on first container
start via the `docker-entrypoint-initdb.d` mount (see `init/`). Init scripts
only run against an empty data volume — if you change `001_schema.sql` after
the volume already exists, drop the `timescaledb_data` volume to re-apply it.

- `init/001_schema.sql`: `telemetry` hypertable (1-day chunks), a `CHECK`
  constraint on `state` (`running`/`idle`/`fault`), indexes on
  `(machine_id, time DESC)` and `(line, time DESC)` for the dashboard's query
  patterns, and a 30-day retention policy.
- `init/002_anomaly_detection.sql`: `telemetry_anomaly_scores` view, rolling
  z-score per machine, flags `is_anomaly` independently of the simulator's
  `state` label.
- `init/003_kpis.sql`: `machine_kpis(from, to)` function, per machine
  availability (running time / observed time), minutes running/idle/fault and
  energy in kWh over a time range. Used by the dashboard's KPI table.

Init scripts are idempotent (`CREATE OR REPLACE`) from `002` on, so a new one
can be applied to an existing volume without dropping it:
```bash
docker compose exec -T timescaledb sh -c 'psql -v ON_ERROR_STOP=1 -U $POSTGRES_USER -d $POSTGRES_DB' < storage/init/003_kpis.sql
```

## Check
`tests/check_kpis.sql` inserts known samples in a transaction, asserts the
exact `machine_kpis()` output and rolls back (no data left behind). Same
command as above with `storage/tests/check_kpis.sql`; prints
`machine_kpis check passed` or fails with the wrong value.
