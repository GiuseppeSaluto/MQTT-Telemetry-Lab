"""
Multi-machine simulator: publishes telemetry over MQTT with drift, gaussian
noise and occasional anomalies. Reads machine/line/threshold config from
config/machines.yaml.

TODO:
- load config/machines.yaml (lines -> machines -> thresholds)
- per machine: generate temperature, vibration, rpm, power_consumption, state
  (running / idle / fault) with drift + gaussian noise + occasional spikes
- publish each machine's telemetry as JSON on factory/{line}/{machine_id}/telemetry
- run on a loop / interval, one publish cycle per tick across all machines
"""


def main() -> None:
    raise NotImplementedError("Implement the simulator.")


if __name__ == "__main__":
    main()
