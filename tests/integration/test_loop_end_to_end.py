import pytest

from maxxair_fan import main
from maxxair_fan.backends import (
    FakeIRBackend,
    FakeSensorBackend,
    InMemoryFirebaseBackend,
    wrap_ir_backend,
)

pytestmark = pytest.mark.integration


def test_loop_end_to_end_ramp_and_cooldown():
    sensor = FakeSensorBackend(series=[72.0, 73.0, 74.5, 72.0])
    ir = wrap_ir_backend(FakeIRBackend())
    fb = InMemoryFirebaseBackend({"fans": {"fan1": {"targetTemp": 72.0, "direction": "in"}}})

    target = 72.0
    direction = "in"
    last_temp = None
    last_time = None
    now = 1000.0

    for _ in range(4):
        target, direction, last_temp, last_time = main.run_loop_iteration(
            target,
            direction,
            last_temp,
            last_time,
            sensor_be=sensor,
            ir_be=ir,
            fb_be=fb,
            now=now,
        )
        now += 1.0

    assert ir.inner.sent == ["fan_off.ir", "fan_on_in_20.ir", "fan_on_in_100.ir", "fan_off.ir"]
    node = fb.get("fans/fan1")
    assert node["currentTemp"] == 72.0
    assert node["sensorOk"] is True


def test_loop_direction_change_resends_ir():
    sensor = FakeSensorBackend(series=[75.0, 75.0])
    ir = wrap_ir_backend(FakeIRBackend())
    fb = InMemoryFirebaseBackend({"fans": {"fan1": {"targetTemp": 72.0, "direction": "in"}}})

    main.run_loop_iteration(72.0, "in", None, None, sensor, ir, fb, now=1000.0)
    fb.patch("fans/fan1", {"direction": "out"})
    main.run_loop_iteration(72.0, "in", 75.0, 1000.0, sensor, ir, fb, now=1001.0)

    assert ir.inner.sent == ["fan_on_in_100.ir", "fan_on_out_100.ir"]
