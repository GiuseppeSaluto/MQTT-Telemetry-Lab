// Ingestion service: MQTT subscriber -> TimescaleDB writer.

use std::env;
use std::io::IsTerminal;
use std::time::Duration;

use chrono::{DateTime, Utc};
use rumqttc::{AsyncClient, Event, MqttOptions, Packet, QoS};
use serde::Deserialize;
use sqlx::postgres::PgConnectOptions;
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

// Data errors (SQLSTATE class 22 data exception, 23 constraint violation, e.g.
// an unknown `state`) won't succeed on retry; anything else (DB down, network)
// is treated as transient.
fn is_bad_data(e: &sqlx::Error) -> bool {
    let code = e.as_database_error().and_then(|db| db.code());
    code.is_some_and(|c| c.starts_with("22") || c.starts_with("23"))
}

async fn insert_telemetry(pool: &PgPool, t: &Telemetry) -> Result<(), sqlx::Error> {
    sqlx::query(
        "INSERT INTO telemetry (time, line, machine_id, temperature, vibration, rpm, power_consumption, state)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
         ON CONFLICT DO NOTHING",
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
    // colours only on a terminal, not in `docker logs` or a file
    tracing_subscriber::fmt()
        .with_ansi(std::io::stdout().is_terminal())
        .init();

    // Reads the standard libpq env vars (PGHOST, PGPORT, PGUSER, PGPASSWORD,
    // PGDATABASE): no connection URL to build, so no escaping of the password.
    // Retried here rather than crashing: after a DB outage Docker's restart
    // backoff would otherwise delay recovery by up to a minute.
    let pool = loop {
        match PgPool::connect_with(PgConnectOptions::new()).await {
            Ok(pool) => break pool,
            Err(e) => {
                warn!("failed to connect to TimescaleDB, retrying in 2 s: {e}");
                tokio::time::sleep(Duration::from_secs(2)).await;
            }
        }
    };
    info!("connected to TimescaleDB");

    let mqtt_host = env::var("MQTT_HOST").unwrap_or_else(|_| "mosquitto".into());
    let mqtt_port: u16 = env::var("MQTT_PORT")
        .ok()
        .and_then(|p| p.parse().ok())
        .unwrap_or(1883);

    let client_id = env::var("MQTT_CLIENT_ID").unwrap_or_else(|_| "ingestion".into());
    let mut mqttoptions = MqttOptions::new(client_id, mqtt_host, mqtt_port);
    mqttoptions.set_keep_alive(Duration::from_secs(5));
    // At-least-once delivery: the broker keeps our session and queues QoS 1
    // messages while we're down, and a message is acked only once it's stored.
    mqttoptions.set_clean_session(false);
    mqttoptions.set_manual_acks(true);

    // poll() hands out already-buffered incoming messages before it reads our
    // requests, so after an outage a burst of redelivered messages queues one
    // ack each. The channel must hold the broker's whole in-flight window
    // (max_inflight_messages in mosquitto.conf), or ack().await blocks the
    // loop that should drain it and the connection dies on keepalive.
    let (client, mut eventloop) = AsyncClient::new(mqttoptions, 100);

    let mut sigterm =
        signal(SignalKind::terminate()).expect("failed to install SIGTERM handler");

    loop {
        tokio::select! {
            event = eventloop.poll() => {
                match event {
                    // Subscribing again on every ConnAck is harmless with a persistent
                    // session and covers the first connect or a broker that lost it.
                    Ok(Event::Incoming(Packet::ConnAck(_))) => {
                        if let Err(e) = client.subscribe("factory/+/+/telemetry", QoS::AtLeastOnce).await {
                            error!("failed to subscribe: {e}");
                        } else {
                            info!("subscribed to factory/+/+/telemetry");
                        }
                    }
                    Ok(Event::Incoming(Packet::Publish(publish))) => {
                        match serde_json::from_slice::<Telemetry>(&publish.payload) {
                            Ok(telemetry) => match insert_telemetry(&pool, &telemetry).await {
                                Ok(()) => {}
                                Err(e) if is_bad_data(&e) => error!("rejected telemetry, dropping it: {e}"),
                                Err(e) => {
                                    // ponytail: crash instead of retrying in-process. The message
                                    // stays unacked, Docker restarts us (restart: on-failure) and the
                                    // broker redelivers it on reconnect. Ceiling: the broker queue
                                    // (max_queued_messages in mosquitto.conf) while we're down;
                                    // upgrade path is a retrying writer task fed by a channel.
                                    error!("failed to insert telemetry, exiting so the broker redelivers it: {e}");
                                    std::process::exit(1);
                                }
                            },
                            Err(e) => warn!("failed to parse telemetry payload, dropping it: {e}"),
                        }
                        if let Err(e) = client.ack(&publish).await {
                            error!("failed to ack message: {e}");
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
