"""
Evaluate anomaly_scores() on real, labelled sensor data: SKAB, the Skoltech
Anomaly Benchmark (https://github.com/waico/SKAB, GPL-3.0, not redistributed
here: downloaded on demand into storage/.skab/, which is gitignored).

Each SKAB experiment (a pump testbed, ~1 sample/s, one labelled anomaly) is
loaded as one machine into a throwaway TimescaleDB built from storage/init, so
the detector measured is exactly the production one. Needs Docker.

    python3 storage/eval_skab.py
"""

import csv
import json
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / ".skab"
API = "https://api.github.com/repos/waico/SKAB/contents/data/"
FOLDERS = ["valve1", "valve2", "other", "anomaly-free"]
IMAGE = "timescale/timescaledb:2.28.3-pg16"
CONTAINER = "skab-eval"
ONSET_TOLERANCE_S = 60  # an alarm within this long after the labelled start counts as detected


def download() -> list[Path]:
    files = []
    for folder in FOLDERS:
        with urllib.request.urlopen(API + folder) as resp:
            listing = json.load(resp)
        for entry in listing:
            if not entry["name"].endswith(".csv"):
                continue
            path = CACHE / folder / entry["name"]
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                urllib.request.urlretrieve(entry["download_url"], path)
            files.append(path)
    return sorted(files)


def to_rows(path: Path) -> tuple[list[list], list[list]]:
    """SKAB columns -> telemetry rows, plus (machine_id, time, anomaly) labels."""
    machine = f"{path.parent.name}_{path.stem}"
    telemetry, labels = [], []
    with path.open() as f:
        for r in csv.DictReader(f, delimiter=";"):
            ts = r["datetime"] + "+00"
            telemetry.append([
                ts, "skab", machine,
                r["Temperature"], r["Accelerometer1RMS"],
                "",  # no rpm in SKAB
                float(r["Current"]) * float(r["Voltage"]) / 1000,  # kW
                "running",  # no operating-state labels; nothing is excluded as idle
            ])
            if "anomaly" in r:
                labels.append([machine, ts, int(float(r["anomaly"]))])
    return telemetry, labels


def psql(sql: str, stdin: str | None = None) -> str:
    return subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-U", "postgres", "-d", "telemetry",
         "-v", "ON_ERROR_STOP=1", "-At", "-c", sql],
        input=stdin, capture_output=True, text=True, check=True,
    ).stdout


def copy_in(table: str, rows: list[list]) -> None:
    lines = "\n".join(",".join(str(v) for v in row) for row in rows) + "\n"
    psql(f"\\copy {table} FROM stdin (FORMAT csv, NULL '')", lines)


EVAL_SQL = f"""
WITH scored AS (
    SELECT a.machine_id, a.time, a.is_anomaly, l.anomaly
    FROM anomaly_scores('-infinity', 'infinity') a
    LEFT JOIN skab_labels l USING (machine_id, time)
),
onsets AS (
    SELECT machine_id, min(time) AS onset FROM skab_labels WHERE anomaly = 1 GROUP BY machine_id
),
events AS (
    SELECT o.machine_id,
           min(s.time) FILTER (WHERE s.is_anomaly
               AND s.time BETWEEN o.onset AND o.onset + interval '{ONSET_TOLERANCE_S} seconds') AS first_alarm,
           o.onset
    FROM onsets o JOIN scored s USING (machine_id)
    GROUP BY o.machine_id, o.onset
),
-- false alarms: normal operation before the labelled onset, plus the
-- anomaly-free recording (after an anomaly the return to normal is a change
-- too, so that stretch is left out)
normal AS (
    SELECT s.* FROM scored s LEFT JOIN onsets o USING (machine_id)
    WHERE o.onset IS NULL OR s.time < o.onset
)
SELECT json_build_object(
    'experiments', (SELECT count(*) FROM events),
    'detected', (SELECT count(first_alarm) FROM events),
    'detected_ids', (SELECT string_agg(machine_id, ' ' ORDER BY machine_id) FROM events WHERE first_alarm IS NOT NULL),
    'median_delay_s', (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM first_alarm - onset)) FROM events),
    'normal_hours', (SELECT round(count(*) / 3600.0, 2) FROM normal),
    'false_alarms', (SELECT count(*) FILTER (WHERE is_anomaly) FROM normal),
    'tp', (SELECT count(*) FILTER (WHERE is_anomaly AND anomaly = 1) FROM scored),
    'fp', (SELECT count(*) FILTER (WHERE is_anomaly AND anomaly = 0) FROM scored),
    'fn', (SELECT count(*) FILTER (WHERE NOT is_anomaly AND anomaly = 1) FROM scored)
);
"""


def main() -> None:
    files = download()
    print(f"{len(files)} SKAB files in {CACHE}")

    subprocess.run(["docker", "rm", "-f", CONTAINER], check=False, capture_output=True)
    subprocess.run(
        ["docker", "run", "-d", "--rm", "--name", CONTAINER, "-e", "POSTGRES_PASSWORD=x",
         "-e", "POSTGRES_DB=telemetry", "-v", f"{ROOT / 'init'}:/docker-entrypoint-initdb.d:ro", IMAGE],
        check=True, stdout=subprocess.DEVNULL,  # stderr left visible, e.g. "is the daemon running?"
    )
    try:
        # the entrypoint restarts postgres after the init scripts: wait for the last one's function
        for _ in range(60):
            try:
                if psql("SELECT count(*) FROM pg_proc WHERE proname = 'machine_kpis'").strip() == "1":
                    break
            except subprocess.CalledProcessError:
                pass
            time.sleep(2)
        time.sleep(3)

        psql("CREATE TABLE skab_labels (machine_id TEXT, time TIMESTAMPTZ, anomaly INT, PRIMARY KEY (machine_id, time))")
        for path in files:
            telemetry, labels = to_rows(path)
            copy_in("telemetry (time, line, machine_id, temperature, vibration, rpm, power_consumption, state)", telemetry)
            if labels:
                copy_in("skab_labels", labels)

        r = json.loads(psql(EVAL_SQL))
    finally:
        subprocess.run(["docker", "rm", "-f", CONTAINER], check=False, capture_output=True)

    precision = r["tp"] / (r["tp"] + r["fp"]) if r["tp"] + r["fp"] else 0.0
    recall = r["tp"] / (r["tp"] + r["fn"]) if r["tp"] + r["fn"] else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    print(f"anomalies detected within {ONSET_TOLERANCE_S} s of the labelled start: "
          f"{r['detected']}/{r['experiments']} ({r['detected_ids'] or '-'})")
    print(f"median detection delay: {r['median_delay_s']} s")
    print(f"false alarms in normal operation: {r['false_alarms']} in {r['normal_hours']} h")
    print(f"per sample (SKAB's usual metric): precision {precision:.2f}, recall {recall:.2f}, F1 {f1:.2f}")


if __name__ == "__main__":
    main()
