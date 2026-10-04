# Storage

TimescaleDB schema and init scripts, run automatically on first container
start via the `docker-entrypoint-initdb.d` mount (see `init/`). Init scripts
only run against an empty data volume — if you change `001_schema.sql` after
the volume already exists, drop the `timescaledb_data` volume to re-apply it.

- `init/001_schema.sql`: `telemetry` hypertable (1-day chunks), a `CHECK`
  constraint on `state` (`running`/`idle`/`fault`), indexes on
  `(machine_id, time DESC)` and `(line, time DESC)` for the dashboard's query
  patterns, and a 30-day retention policy.
- `init/002_anomaly_detection.sql`: `anomaly_scores(from, to)` function,
  rolling 5-minute z-score per machine, flags `is_anomaly` independently of
  the simulator's fault label. Reads only the requested range plus 5 minutes
  of warm-up, and skips idle samples (a stopped machine is not an anomaly).
- `init/003_kpis.sql`: `machine_kpis(from, to)` function, per machine
  availability (running time / observed time), minutes running/idle/fault and
  energy in kWh over a time range. Used by the dashboard's KPI table.

Init scripts are idempotent from `002` on (`CREATE OR REPLACE`), so a new or
changed one can be applied to an existing volume without dropping it:
```bash
docker compose exec -T timescaledb sh -c 'psql -v ON_ERROR_STOP=1 -U $POSTGRES_USER -d $POSTGRES_DB' < storage/init/003_kpis.sql
```

## Check
`tests/check_kpis.sql` and `tests/check_anomaly_scores.sql` insert known
samples in a transaction, assert the exact function output and roll back (no
data left behind). Run them with the same command as above; each prints
`... check passed` or fails naming what is wrong.
