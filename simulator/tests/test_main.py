"""Unit tests for the simulator's pure logic: state transitions, value
generation, and config loading. No MQTT/network involved."""

import numpy as np
import pytest

import main as sim


class FakeRng:
    """Deterministic stand-in for np.random.Generator: feed exact return
    values instead of relying on a real seed to hit a specific branch."""

    def __init__(self, randoms=None, normal=0.0, uniform=1.0):
        self._randoms = list(randoms or [])
        self._normal = normal
        self._uniform = uniform

    def random(self):
        return self._randoms.pop(0)

    def normal(self, loc=0.0, scale=1.0):
        return self._normal

    def uniform(self, low, high):
        return self._uniform


def make_machine(**overrides):
    defaults = {
        "id": "machine_X",
        "line": "line1",
        "type": "extruder",
        "temperature_max": 85.0,
        "vibration_max": 4.5,
        "rpm_baseline": 1200.0,
        "power_baseline": 45.0,
    }
    defaults.update(overrides)
    return sim.MachineState(**defaults)


# -- load_machines --------------------------------------------------------


def test_load_machines_reads_real_config():
    machines = sim.load_machines(sim.CONFIG_PATH)

    assert [m.id for m in machines] == ["machine_A", "machine_B", "machine_C"]
    assert [m.line for m in machines] == ["line1", "line1", "line2"]

    machine_a = machines[0]
    assert machine_a.type == "extruder"
    assert machine_a.temperature_max == 85
    assert machine_a.vibration_max == 4.5
    # rpm/power come from TYPE_PROFILES, keyed by machine type
    assert machine_a.rpm_baseline == sim.TYPE_PROFILES["extruder"]["rpm"]


# -- _next_state ------------------------------------------------------------


def test_running_stays_running_below_all_thresholds():
    machine = make_machine(state="running")
    rng = FakeRng(randoms=[0.99, 0.99])  # above ANOMALY_CHANCE and IDLE_CHANCE

    assert sim._next_state(machine, rng) == "running"


def test_running_switches_to_idle():
    machine = make_machine(state="running")
    rng = FakeRng(randoms=[0.5, 0.01])  # no anomaly, but below IDLE_CHANCE

    assert sim._next_state(machine, rng) == "idle"


def test_running_switches_to_fault_and_sets_countdown():
    machine = make_machine(state="running")
    rng = FakeRng(randoms=[0.001])  # below ANOMALY_CHANCE

    assert sim._next_state(machine, rng) == "fault"
    assert machine.spike_ticks_left == sim.SPIKE_DURATION_TICKS - 1


def test_fault_continues_while_countdown_remains():
    machine = make_machine(state="fault", spike_ticks_left=2)
    rng = FakeRng()  # must not be consulted while a spike is running

    assert sim._next_state(machine, rng) == "fault"
    assert machine.spike_ticks_left == 1


def test_fault_ends_when_countdown_reaches_zero():
    machine = make_machine(state="fault", spike_ticks_left=0)
    rng = FakeRng()

    assert sim._next_state(machine, rng) == "running"


def test_idle_resumes_running():
    machine = make_machine(state="idle")
    rng = FakeRng(randoms=[0.01])  # below RESUME_CHANCE

    assert sim._next_state(machine, rng) == "running"


def test_idle_stays_idle():
    machine = make_machine(state="idle")
    rng = FakeRng(randoms=[0.99])  # above RESUME_CHANCE

    assert sim._next_state(machine, rng) == "idle"


# -- _generate_values --------------------------------------------------------


def test_fault_values_exceed_thresholds():
    machine = make_machine(state="fault")
    rng = FakeRng(normal=0.0, uniform=1.1)  # fixed 10% over threshold

    temperature, vibration, rpm, power = sim._generate_values(machine, rng)

    assert temperature > machine.temperature_max
    assert vibration > machine.vibration_max
    assert rpm == 0.0
    assert power > machine.power_baseline


def test_idle_values_are_near_zero_activity():
    machine = make_machine(state="idle")
    rng = FakeRng(normal=0.0, uniform=1.0)

    temperature, vibration, rpm, power = sim._generate_values(machine, rng)

    assert rpm == 0.0
    assert power == pytest.approx(machine.power_baseline * 0.05)
    assert temperature < machine.temperature_baseline
    assert vibration < machine.vibration_baseline


def test_running_values_stay_within_plausible_bounds():
    # property-style smoke test with a real seeded RNG across many ticks
    machine = make_machine(state="running")
    rng = np.random.default_rng(42)

    for _ in range(500):
        temperature, vibration, rpm, power = sim._generate_values(machine, rng)
        assert 0.0 <= temperature <= machine.temperature_max * 1.5
        assert vibration >= 0.0
        assert rpm >= 0.0
        assert power >= 0.0


# -- step ---------------------------------------------------------------


def test_step_produces_expected_payload_shape():
    machine = make_machine()
    rng = np.random.default_rng(0)

    payload = sim.step(machine, rng)

    assert set(payload) == {
        "time",
        "line",
        "machine_id",
        "temperature",
        "vibration",
        "rpm",
        "power_consumption",
        "state",
    }
    assert payload["machine_id"] == machine.id
    assert payload["line"] == machine.line
    assert payload["state"] in {"running", "idle", "fault"}
