# Ingestion

Rust service: subscribes to `factory/+/+/telemetry` on MQTT (`rumqttc`),
deserializes each JSON payload, and writes it into TimescaleDB (`sqlx`,
runtime-checked queries — no compile-time DB connection required to build).

## Error handling
The service never crashes on a single bad message:
- malformed JSON → logged (`warn!`) and dropped
- DB insert failure (e.g. `state` outside `running`/`idle`/`fault`, rejected
  by the schema's `CHECK` constraint) → logged (`error!`) and skipped
- MQTT connection drop → logged (`warn!`), `rumqttc` reconnects automatically
  on the next `poll()`

## Config (env vars)
| Var | Default | Meaning |
|---|---|---|
| `MQTT_HOST` | `mosquitto` | broker host |
| `MQTT_PORT` | `1883` | broker port |
| `POSTGRES_HOST` | `timescaledb` | DB host |
| `POSTGRES_PORT` | `5432` | DB port |
| `POSTGRES_USER` | `iot` | DB user |
| `POSTGRES_PASSWORD` | `iot` | DB password |
| `POSTGRES_DB` | `telemetry` | DB name |

## Build/run locally
```bash
cargo build --release
MQTT_HOST=localhost POSTGRES_HOST=localhost ./target/release/ingestion
```
