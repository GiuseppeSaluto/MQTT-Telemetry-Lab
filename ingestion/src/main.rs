// Ingestion service: MQTT subscriber -> TimescaleDB writer.

use std::env;
use std::time::Duration;

use chrono::{DateTime, Utc};
use rumqttc::{AsyncClient, Event, MqttOptions, Packet, QoS};
use serde::Deserialize;
use sqlx::PgPool;
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

fn database_url() -> String {
    let user = env::var("POSTGRES_USER").unwrap_or_else(|_| "iot".into());
    let password = env::var("POSTGRES_PASSWORD").unwrap_or_else(|_| "iot".into());
    let db = env::var("POSTGRES_DB").unwrap_or_else(|_| "telemetry".into());
    let host = env::var("POSTGRES_HOST").unwrap_or_else(|_| "timescaledb".into());
    let port = env::var("POSTGRES_PORT").unwrap_or_else(|_| "5432".into());
    format!("postgres://{user}:{password}@{host}:{port}/{db}").to_string()
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

    loop {
        match eventloop.poll().await {
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
}
