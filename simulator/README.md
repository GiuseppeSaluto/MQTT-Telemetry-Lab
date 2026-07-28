# Simulator

Python service that publishes fake but plausible telemetry over MQTT for the
machines/lines defined in `config/machines.yaml` — no machine/line/threshold
is hardcoded here.

## How the data is generated
Each machine is a small state machine (`running` / `idle` / `fault`) with
random transitions (see `ANOMALY_CHANCE`, `IDLE_CHANCE`, `RESUME_CHANCE` in
`main.py`). Independently of state, temperature and vibration follow a slow
mean-reverting drift plus fast gaussian noise, so values move continuously
across state changes instead of jumping. `rpm`/`power_consumption` have no
thresholds in `machines.yaml`, so `TYPE_PROFILES` gives each machine type
(`extruder`/`packaging`/`assembly`) a plausible baseline to drift around —
it's the one place with invented numbers, change it if you want different
behavior.

## Config (env vars)
| Var | Default | Meaning |
|---|---|---|
| `MACHINES_CONFIG` | `config/machines.yaml` (repo-relative) | path to the machines config |
| `MQTT_HOST` | `mosquitto` | broker host |
| `MQTT_PORT` | `1883` | broker port |
| `SIM_INTERVAL_SECONDS` | `2` | seconds between publish ticks |

## Run locally (without Docker)
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
MQTT_HOST=localhost .venv/bin/python main.py
```
