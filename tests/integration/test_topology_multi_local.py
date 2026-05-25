from maxxair_fan import main
from maxxair_fan.backends import (
    FakeIRBackend,
    FakeSensorBackend,
    InMemoryFirebaseBackend,
    build_fan_unit,
)
from maxxair_fan.fans_config import FanSpec, LocalFanConfig


def test_topology_multi_local_independent_control():
    fb = InMemoryFirebaseBackend(
        {
            "fans": {
                "fan1": {"targetTemp": 72.0, "direction": "in"},
                "fan2": {"targetTemp": 68.0, "direction": "out"},
            }
        }
    )
    sensor1 = FakeSensorBackend(temp=75.0)
    sensor2 = FakeSensorBackend(temp=70.0)
    ir1 = FakeIRBackend()
    ir2 = FakeIRBackend()

    unit1 = build_fan_unit(
        FanSpec(id="fan1", firebase_node="fans/fan1", local=LocalFanConfig()),
        fake_sensor=sensor1,
        fake_ir=ir1,
        dedupe_ir=False,
    )
    unit2 = build_fan_unit(
        FanSpec(id="fan2", firebase_node="fans/fan2", local=LocalFanConfig()),
        fake_sensor=sensor2,
        fake_ir=ir2,
        dedupe_ir=False,
    )

    main.run_multi_fan_iteration([unit1, unit2], fb, now=1000.0)

    assert ir1.sent == ["fan_on_in_100.ir"]
    assert ir2.sent == ["fan_on_out_80.ir"]
    assert fb.get("fans/fan1")["currentTemp"] == 75.0
    assert fb.get("fans/fan2")["currentTemp"] == 70.0
