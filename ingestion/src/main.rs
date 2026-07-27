// Ingestion service: MQTT subscriber -> TimescaleDB writer.
// TODO:
// - connect to the MQTT broker (rumqttc)
// - subscribe to factory/+/+/telemetry
// - deserialize the JSON payload
// - write rows into TimescaleDB (sqlx / tokio-postgres)
// - log/handle errors without crashing the service

fn main() {
    println!("ingestion service - not implemented yet");
}
