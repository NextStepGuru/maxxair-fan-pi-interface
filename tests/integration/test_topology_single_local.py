from pathlib import Path

from maxxair_fan import config, main
from maxxair_fan.backends import (
    FakeIRBackend,
    FakeSensorBackend,
    InMemoryFirebaseBackend,
    build_fan_unit,
)
from maxxair_fan.fans_config import load_fans_config

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "topologies" / "single_local.json"


def test_topology_single_local_parity(monkeypatch):
    monkeypatch.setattr(config, "FANS_CONFIG", str(FIXTURE))
    specs = load_fans_config()
    fb = InMemoryFirebaseBackend(
        {"fans": {"fan1": {"targetTemp": 70.0, "direction": "out"}}}
    )
    sensor = FakeSensorBackend(temp=75.0)
    ir = FakeIRBackend()
    unit = build_fan_unit(specs[0], fake_sensor=sensor, fake_ir=ir, dedupe_ir=False)

    main.run_multi_fan_iteration([unit], fb, now=1000.0)

    assert ir.sent == ["fan_on_out_100.ir"]
    node = fb.get("fans/fan1")
    assert node["currentTemp"] == 75.0
    assert node["online"] is True
