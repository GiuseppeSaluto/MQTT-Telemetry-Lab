"""
Multi-machine simulator: publishes telemetry over MQTT with drift, gaussian
noise and occasional anomalies. Reads machine/line/threshold config from
config/machines.yaml.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import paho.mqtt.client as mqtt
import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("simulator")

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "machines.yaml"
CONFIG_PATH = Path(os.environ.get("MACHINES_CONFIG", str(DEFAULT_CONFIG_PATH)))
MQTT_HOST = os.environ.get("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
TICK_SECONDS = float(os.environ.get("SIM_INTERVAL_SECONDS", "2"))

# rpm / power_consumption have no thresholds in machines.yaml, so we give each
# machine type a plausible baseline to drift and add noise around.
TYPE_PROFILES = {
    "extruder": {"rpm": 1200.0, "power_consumption": 45.0},
    "packaging": {"rpm": 300.0, "power_consumption": 8.0},
    "assembly": {"rpm": 150.0, "power_consumption": 5.0},
}

ANOMALY_CHANCE = 0.03  # probability per tick, while running, of starting a fault spike
IDLE_CHANCE = 0.05  # probability per tick, while running, of switching to idle
RESUME_CHANCE = 0.2  # probability per tick, while idle, of switching back to running
SPIKE_DURATION_TICKS = 3


@dataclass
class MachineState:
    id: str
    line: str
    type: str
    temperature_max: float
    vibration_max: float
    rpm_baseline: float
    power_baseline: float
    state: str = "running"
    temperature_drift: float = 0.0
    vibration_drift: float = 0.0
    spike_ticks_left: int = 0

    @property
    def temperature_baseline(self) -> float:
        return self.temperature_max * 0.65

    @property
    def vibration_baseline(self) -> float:
        return self.vibration_max * 0.5


def load_machines(config_path: Path) -> list[MachineState]:
    with config_path.open() as f:
        config = yaml.safe_load(f)

    machines = []
    for line_id, line in config["lines"].items():
        for machine in line["machines"]:
            profile = TYPE_PROFILES[machine["type"]]
            machines.append(
                MachineState(
                    id=machine["id"],
                    line=line_id,
                    type=machine["type"],
                    temperature_max=machine["thresholds"]["temperature_max"],
                    vibration_max=machine["thresholds"]["vibration_max"],
                    rpm_baseline=profile["rpm"],
                    power_baseline=profile["power_consumption"],
                )
            )
    return machines


def _next_state(machine: MachineState, rng: np.random.Generator) -> str:
    if machine.spike_ticks_left > 0:
        machine.spike_ticks_left -= 1
        return "fault"
    if machine.state == "fault":
        return "running"  # spike just ended
    if machine.state == "idle":
        return "running" if rng.random() < RESUME_CHANCE else "idle"

    # running
    if rng.random() < ANOMALY_CHANCE:
        machine.spike_ticks_left = SPIKE_DURATION_TICKS - 1  # this tick is the first fault tick
        return "fault"
    if rng.random() < IDLE_CHANCE:
        return "idle"
    return "running"


def _generate_values(machine: MachineState, rng: np.random.Generator) -> tuple[float, float, float, float]:
    # slow mean-reverting drift + fast gaussian noise, updated every tick
    # regardless of state so it keeps evolving smoothly across transitions.
    machine.temperature_drift += rng.normal(0, 0.3) - 0.05 * machine.temperature_drift
    machine.vibration_drift += rng.normal(0, 0.05) - 0.05 * machine.vibration_drift

    if machine.state == "fault":
        temperature = machine.temperature_max * rng.uniform(1.02, 1.15)
        vibration = machine.vibration_max * rng.uniform(1.02, 1.15)
        rpm = 0.0
        power_consumption = machine.power_baseline * rng.uniform(1.1, 1.3)
    elif machine.state == "idle":
        temperature = max(20.0, machine.temperature_baseline * 0.5 + machine.temperature_drift)
        vibration = max(0.0, machine.vibration_baseline * 0.2 + machine.vibration_drift * 0.2)
        rpm = 0.0
        power_consumption = machine.power_baseline * 0.05
    else:
        temperature = max(20.0, machine.temperature_baseline + machine.temperature_drift + rng.normal(0, 0.5))
        vibration = max(0.0, machine.vibration_baseline + machine.vibration_drift + rng.normal(0, 0.1))
        rpm = max(0.0, machine.rpm_baseline + rng.normal(0, machine.rpm_baseline * 0.02))
        power_consumption = max(0.0, machine.power_baseline + rng.normal(0, machine.power_baseline * 0.03))

    return temperature, vibration, rpm, power_consumption


def step(machine: MachineState, rng: np.random.Generator) -> dict:
    machine.state = _next_state(machine, rng)
    temperature, vibration, rpm, power_consumption = _generate_values(machine, rng)

    return {
        "time": datetime.now(timezone.utc).isoformat(),
        "line": machine.line,
        "machine_id": machine.id,
        "temperature": round(temperature, 2),
        "vibration": round(vibration, 3),
        "rpm": round(rpm, 1),
        "power_consumption": round(power_consumption, 2),
        "state": machine.state,
    }


def connect_with_retry(client: mqtt.Client, host: str, port: int, attempts: int = 10, delay: float = 3.0) -> None:
    for attempt in range(1, attempts + 1):
        try:
            client.connect(host, port)
            return
        except OSError as exc:
            logger.warning("MQTT connect attempt %d/%d to %s:%d failed: %s", attempt, attempts, host, port, exc)
            time.sleep(delay)
    raise RuntimeError(f"could not connect to MQTT broker at {host}:{port}")


def _raise_keyboard_interrupt(_signum, _frame) -> None:
    raise KeyboardInterrupt


def main() -> None:
    # docker stop sends SIGTERM, which by default kills the process before
    # our try/finally below would run - route it through the same shutdown
    # path as Ctrl+C (SIGINT) instead.
    signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)

    machines = load_machines(CONFIG_PATH)
    logger.info("loaded %d machines from %s", len(machines), CONFIG_PATH)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    connect_with_retry(client, MQTT_HOST, MQTT_PORT)
    client.loop_start()

    rng = np.random.default_rng()

    try:
        while True:
            for machine in machines:
                payload = step(machine, rng)
                topic = f"factory/{machine.line}/{machine.id}/telemetry"
                client.publish(topic, json.dumps(payload))
                logger.debug("published %s: %s", topic, payload)
            time.sleep(TICK_SECONDS)
    except KeyboardInterrupt:
        logger.info("shutting down")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
