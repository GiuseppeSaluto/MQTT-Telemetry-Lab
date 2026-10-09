# Ingestion

Rust service: subscribes to `factory/+/+/telemetry` on MQTT (`rumqttc`),
deserializes each JSON payload, and writes it into TimescaleDB (`sqlx`,
runtime-checked queries — no compile-time DB connection required to build).

## Delivery and error handling
At-least-once: the simulator publishes with QoS 1, the service keeps a
persistent MQTT session (`clean_session = false`) and acks each message only
after it's handled, so the broker queues messages while the service or the
database is down and redelivers anything not acked.
- malformed JSON → logged (`warn!`), acked and dropped
- data the schema rejects (SQLSTATE class 22/23, e.g. a `state` outside
  `running`/`idle`/`fault`) → logged (`error!`), acked and dropped: retrying
  can't fix it, and not acking it would crash-loop on the same message
- any other insert failure (database down) → logged and the process exits
  without acking; Docker restarts it, it retries the DB connection every 2 s,
  and the broker redelivers the message on reconnect
- duplicates from redelivery → ignored by `ON CONFLICT DO NOTHING` on the
  unique `(machine_id, time)` index
- MQTT connection drop → logged (`warn!`), `rumqttc` reconnects and the
  service resubscribes on every `ConnAck`

Measured locally (3 machines, one sample each every 2 s): with the database
stopped for 60 s, 0 samples lost (46/46 per machine) against 93 lost before
this design; with the service stopped for 30 s, 0 lost and 0 duplicates.
Limit: queued messages live in the broker's memory (`max_queued_messages`,
~18 h at this rate), so a broker restart during an outage loses them.

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

## Image
Built on Alpine, so the binary is statically linked against musl, and TLS is
rustls (no OpenSSL): the runtime image is `scratch` with only the binary,
8 MB instead of 126 MB on Debian slim, running as uid 65534 rather than root.

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
