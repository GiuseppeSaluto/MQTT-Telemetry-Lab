# Ingestion

Rust service: subscribes to `factory/+/+/telemetry` on MQTT (`rumqttc`),
deserializes each JSON payload, and writes it into TimescaleDB (`sqlx`,
runtime-checked queries — no compile-time DB connection required to build).

## Error handling
The service never crashes on a single bad message:
- malformed JSON → logged (`warn!`) and dropped
- DB insert failure (e.g. `state` outside `running`/`idle`/`fault`, rejected
  by the schema's `CHECK` constraint) → logged (`error!`) and skipped
- MQTT connection drop → logged (`warn!`), `rumqttc` reconnects and the
  service resubscribes on every `ConnAck`

## Config (env vars)
| Var | Default | Meaning |
|---|---|---|
| `MQTT_HOST` | `mosquitto` | broker host |
| `MQTT_PORT` | `1883` | broker port |
| `MQTT_CLIENT_ID` | `ingestion` | MQTT client ID - must be unique per broker connection |
| `PGHOST` | `localhost` | DB host |
| `PGPORT` | `5432` | DB port |
| `PGUSER` | OS user | DB user |
| `PGPASSWORD` | none | DB password |
| `PGDATABASE` | same as `PGUSER` | DB name |

The `PG*` variables are the standard libpq ones, read directly by `sqlx`
(`PgConnectOptions::new()`): no connection URL is built, so the password
needs no escaping. docker-compose maps them from the `POSTGRES_*` values in
`.env`.

## Build/run locally
```bash
cargo build --release
MQTT_HOST=localhost PGHOST=localhost PGUSER=... PGPASSWORD=... PGDATABASE=telemetry \
  ./target/release/ingestion
```

## Tests
Unit tests (`src/main.rs`, `#[cfg(test)] mod tests`) cover telemetry JSON
deserialization — no live broker/DB needed.
```bash
cargo test
cargo clippy --all-targets -- -D warnings
```
