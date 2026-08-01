// Ingestion service: MQTT subscriber -> TimescaleDB writer.

use std::env;
use std::time::Duration;

use chrono::{DateTime, Utc};
use rumqttc::{AsyncClient, Event, MqttOptions, Packet, QoS};
use serde::Deserialize;
use sqlx::PgPool;
use tokio::signal::unix::{signal, SignalKind};
use tracing::{error, info, warn};

#[derive(Debug, Deserialize)]
struct Telemetry {
    time: DateTime<Utc>,
    line: String,
    machine_id: String,
    temperature: f64,
    vibration: f64,
    rpm: f64,
    power_consumption: f64,
    state: String,
}

// Takes a lookup function instead of reading `env::var` directly so it can be
// unit tested without touching real (process-global) environment variables.
fn database_url_from(get: impl Fn(&str) -> Option<String>) -> String {
    let user = get("POSTGRES_USER").unwrap_or_else(|| "iot".to_string());
    let password = get("POSTGRES_PASSWORD").unwrap_or_else(|| "iot".to_string());
    let db = get("POSTGRES_DB").unwrap_or_else(|| "telemetry".to_string());
    let host = get("POSTGRES_HOST").unwrap_or_else(|| "timescaledb".to_string());
    let port = get("POSTGRES_PORT").unwrap_or_else(|| "5432".to_string());

    let url = format!("postgres://{user}:{password}@{host}:{port}/{db}");
    url
}

fn database_url() -> String {
    database_url_from(|key| std::env::var(key).ok())
}

async fn insert_telemetry(pool: &PgPool, t: &Telemetry) -> Result<(), sqlx::Error> {
    sqlx::query(
        "INSERT INTO telemetry (time, line, machine_id, temperature, vibration, rpm, power_consumption, state)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
    )
    .bind(t.time)
    .bind(&t.line)
    .bind(&t.machine_id)
    .bind(t.temperature)
    .bind(t.vibration)
    .bind(t.rpm)
    .bind(t.power_consumption)
    .bind(&t.state)
    .execute(pool)
    .await?;
    Ok(())
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt::init();

    let pool = PgPool::connect(&database_url())
        .await
        .expect("failed to connect to TimescaleDB");
    info!("connected to TimescaleDB");

    let mqtt_host = env::var("MQTT_HOST").unwrap_or_else(|_| "mosquitto".into());
    let mqtt_port: u16 = env::var("MQTT_PORT")
        .ok()
        .and_then(|p| p.parse().ok())
        .unwrap_or(1883);

    let mut mqttoptions = MqttOptions::new("ingestion", mqtt_host, mqtt_port);
    mqttoptions.set_keep_alive(Duration::from_secs(5));

    let (client, mut eventloop) = AsyncClient::new(mqttoptions, 10);
    client
        .subscribe("factory/+/+/telemetry", QoS::AtLeastOnce)
        .await
        .expect("failed to subscribe");
    info!("subscribed to factory/+/+/telemetry");

    let mut sigterm =
        signal(SignalKind::terminate()).expect("failed to install SIGTERM handler");

    loop {
        tokio::select! {
            event = eventloop.poll() => {
                match event {
                    Ok(Event::Incoming(Packet::Publish(publish))) => {
                        match serde_json::from_slice::<Telemetry>(&publish.payload) {
                            Ok(telemetry) => {
                                if let Err(e) = insert_telemetry(&pool, &telemetry).await {
                                    error!("failed to insert telemetry: {e}");
                                }
                            }
                            Err(e) => {
                                warn!("failed to parse telemetry payload: {e}");
                            }
                        }
                    }
                    Ok(_) => {}
                    Err(e) => {
                        warn!("MQTT connection error: {e}");
                        tokio::time::sleep(Duration::from_secs(1)).await;
                    }
                }
            }
            _ = tokio::signal::ctrl_c() => {
                info!("received SIGINT, shutting down");
                break;
            }
            _ = sigterm.recv() => {
                info!("received SIGTERM, shutting down");
                break;
            }
        }
    }

    client.disconnect().await.ok();
    pool.close().await;
    info!("shutdown complete");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn database_url_uses_provided_values() {
        let url = database_url_from(|key| match key {
            "POSTGRES_USER" => Some("alice".to_string()),
            "POSTGRES_PASSWORD" => Some("secret".to_string()),
            "POSTGRES_DB" => Some("mydb".to_string()),
            "POSTGRES_HOST" => Some("dbhost".to_string()),
            "POSTGRES_PORT" => Some("5555".to_string()),
            _ => None,
        });

        assert_eq!(url, "postgres://alice:secret@dbhost:5555/mydb");
    }

    #[test]
    fn database_url_falls_back_to_defaults() {
        let url = database_url_from(|_| None);

        assert_eq!(url, "postgres://iot:iot@timescaledb:5432/telemetry");
    }

    #[test]
    fn telemetry_deserializes_valid_payload() {
        let json = r#"{
            "time": "2026-07-27T19:17:48.023858+00:00",
            "line": "line1",
            "machine_id": "machine_A",
            "temperature": 26.83,
            "vibration": 0.4,
            "rpm": 0.0,
            "power_consumption": 2.25,
            "state": "idle"
        }"#;

        let telemetry: Telemetry = serde_json::from_str(json).expect("should deserialize");

        assert_eq!(telemetry.line, "line1");
        assert_eq!(telemetry.machine_id, "machine_A");
        assert_eq!(telemetry.state, "idle");
        assert_eq!(telemetry.temperature, 26.83);
    }

    #[test]
    fn telemetry_rejects_missing_field() {
        let json = r#"{
            "time": "2026-07-27T19:17:48.023858+00:00",
            "line": "line1",
            "machine_id": "machine_A",
            "temperature": 26.83,
            "vibration": 0.4,
            "rpm": 0.0,
            "state": "idle"
        }"#; // missing power_consumption

        let result: Result<Telemetry, _> = serde_json::from_str(json);

        assert!(result.is_err());
    }

    #[test]
    fn telemetry_rejects_malformed_timestamp() {
        let json = r#"{
            "time": "not-a-timestamp",
            "line": "line1",
            "machine_id": "machine_A",
            "temperature": 26.83,
            "vibration": 0.4,
            "rpm": 0.0,
            "power_consumption": 2.25,
            "state": "idle"
        }"#;

        let result: Result<Telemetry, _> = serde_json::from_str(json);

        assert!(result.is_err());
    }
}
