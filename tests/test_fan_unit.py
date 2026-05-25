
import pytest

from maxxair_fan import config
from maxxair_fan.backends import (
    FakeIRBackend,
    FakeSensorBackend,
    InMemoryFirebaseBackend,
    wrap_ir_backend,
)
from maxxair_fan.fan_unit import FanState, FanUnit, build_status_patch
from maxxair_fan.fans_config import FanSpec, LocalFanConfig


@pytest.fixture
def fake_backends():
    sensor = FakeSensorBackend(temp=72.0)
    ir = wrap_ir_backend(FakeIRBackend())
    fb = InMemoryFirebaseBackend()
    yield sensor, ir, fb


def test_build_status_patch_per_fan_crc():
    patch = build_status_patch(
        now_iso="2026-01-01T00:00:00+00:00",
        current_temp=73.0,
        sensor_ok=True,
        ir_ok=True,
        last_ir_command="fan_on_in_40.ir",
        last_error=None,
        sensor_crc_failures=5,
    )
    assert patch["sensorCrcFailures"] == 5


def test_fan_unit_controls_fan_and_patches(fake_backends):
    sensor_be, ir_be, fb_be = fake_backends
    inner_ir = ir_be.inner  # type: ignore[attr-defined]
    spec = FanSpec(id="fan1", firebase_node="fans/fan1", local=LocalFanConfig())
    unit = FanUnit(spec=spec, sensor_be=sensor_be, ir_be=ir_be)

    fb_be.put("fans/fan1", {"targetTemp": 70, "direction": "out"})
    sensor_be.set_temp(75.0)

    state = unit.run_iteration(fb_be, now=1000.0)

    assert state.cached_target_temp == 70.0
    assert state.cached_direction == "out"
    assert state.last_patched_temp == 75.0
    assert inner_ir.sent == ["fan_on_out_100.ir"]
    node = fb_be.get("fans/fan1")
    assert node["currentTemp"] == 75.0


def test_fan_unit_sensor_failure(fake_backends):
    sensor_be, ir_be, fb_be = fake_backends
    spec = FanSpec(id="fan1", firebase_node="fans/fan1", local=LocalFanConfig())
    unit = FanUnit(spec=spec, sensor_be=sensor_be, ir_be=ir_be)

    class NullSensor(FakeSensorBackend):
        def read_temp_f(self):
            return None

    unit.sensor_be = NullSensor()
    state = unit.run_iteration(fb_be, now=1000.0)

    assert state.last_patch_time == 1000.0
    assert fb_be.get("fans/fan1")["sensorOk"] is False


def test_fan_unit_ir_failure(fake_backends):
    sensor_be, _ir_be, fb_be = fake_backends
    sensor_be.set_temp(75.0)
    spec = FanSpec(id="fan1", firebase_node="fans/fan1", local=LocalFanConfig())

    class FailingIR:
        def send(self, filename: str) -> bool:
            return False

    unit = FanUnit(spec=spec, sensor_be=sensor_be, ir_be=wrap_ir_backend(FailingIR()))
    unit.run_iteration(fb_be, now=1000.0)

    node = fb_be.get("fans/fan1")
    assert node["irOk"] is False
    assert "IR send failed" in node["lastError"]


def test_fan_unit_throttles_patch(fake_backends, monkeypatch):
    sensor_be, ir_be, fb_be = fake_backends
    sensor_be.set_temp(72.0)
    monkeypatch.setattr(config, "TEMP_PATCH_THRESHOLD", 0.1)
    monkeypatch.setattr(config, "PATCH_HEARTBEAT_SECONDS", 60)

    spec = FanSpec(id="fan1", firebase_node="fans/fan1", local=LocalFanConfig())
    unit = FanUnit(
        spec=spec,
        sensor_be=sensor_be,
        ir_be=ir_be,
        state=FanState(
            cached_target_temp=72.0,
            cached_direction="in",
            last_patched_temp=72.0,
            last_patch_time=1000.0,
        ),
    )
    unit.run_iteration(fb_be, now=1030.0)

    assert "currentTemp" not in (fb_be.get("fans/fan1") or {})
