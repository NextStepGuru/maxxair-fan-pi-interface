import json
from pathlib import Path

import pytest

from maxxair_fan import config, main
from maxxair_fan.backends import (
    FakeIRBackend,
    FakeSensorBackend,
    InMemoryFirebaseBackend,
    wrap_ir_backend,
)
from maxxair_fan.devtools.replay import parse_fixture_steps

pytestmark = pytest.mark.integration

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_sensor_outage_patches_sensor_ok_during_failure(monkeypatch):
    monkeypatch.setattr(config, "PATCH_HEARTBEAT_SECONDS", 1)
    fixture = json.loads((FIXTURES_DIR / "sensor_outage.json").read_text())
    temps = parse_fixture_steps(fixture["steps"])
    sensor = FakeSensorBackend(series=temps)
    ir = wrap_ir_backend(FakeIRBackend())
    fb = InMemoryFirebaseBackend(
        {
            "fans": {
                "fan1": {
                    "targetTemp": fixture["target"],
                    "direction": fixture["direction"],
                }
            }
        }
    )

    sensor_ok_by_step: list[bool | None] = []
    cached_target = float(fixture["target"])
    cached_direction = fixture["direction"]
    last_temp = None
    last_time = None
    now = 1000.0

    for _ in range(len(temps)):
        cached_target, cached_direction, last_temp, last_time = main.run_loop_iteration(
            cached_target,
            cached_direction,
            last_temp,
            last_time,
            sensor_be=sensor,
            ir_be=ir,
            fb_be=fb,
            now=now,
        )
        node = fb.get("fans/fan1") or {}
        sensor_ok_by_step.append(node.get("sensorOk"))
        now += 1.0

    assert ir.inner.sent == ["fan_on_in_100.ir", "fan_off.ir"]
    assert sensor_ok_by_step == [True, False, False, True]
