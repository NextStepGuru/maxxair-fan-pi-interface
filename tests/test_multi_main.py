
import pytest

from maxxair_fan import config, main
from maxxair_fan.backends import (
    FakeIRBackend,
    FakeSensorBackend,
    InMemoryFirebaseBackend,
    build_fan_unit,
    wrap_ir_backend,
)
from maxxair_fan.fan_unit import FanUnit
from maxxair_fan.fans_config import FanSpec, LocalFanConfig, load_fans_config


@pytest.fixture(autouse=True)
def reset_state():
    main.reset_shutdown_flag()
    yield
    main.reset_shutdown_flag()


def test_run_multi_fan_iteration_two_local_fans():
    fb = InMemoryFirebaseBackend(
        {
            "fans": {
                "fan1": {"targetTemp": 72.0, "direction": "in"},
                "fan2": {"targetTemp": 72.0, "direction": "in"},
            }
        }
    )
    sensor1 = FakeSensorBackend(temp=75.0)
    sensor2 = FakeSensorBackend(temp=73.0)
    ir1 = wrap_ir_backend(FakeIRBackend())
    ir2 = wrap_ir_backend(FakeIRBackend())

    unit1 = FanUnit(
        spec=FanSpec(id="fan1", firebase_node="fans/fan1", local=LocalFanConfig()),
        sensor_be=sensor1,
        ir_be=ir1,
    )
    unit2 = FanUnit(
        spec=FanSpec(id="fan2", firebase_node="fans/fan2", local=LocalFanConfig()),
        sensor_be=sensor2,
        ir_be=ir2,
    )

    main.run_multi_fan_iteration([unit1, unit2], fb, now=1000.0)

    assert ir1.inner.sent == ["fan_on_in_100.ir"]  # type: ignore[attr-defined]
    assert ir2.inner.sent == ["fan_on_in_20.ir"]  # type: ignore[attr-defined]
    assert fb.get("fans/fan1")["currentTemp"] == 75.0
    assert fb.get("fans/fan2")["currentTemp"] == 73.0


def test_main_fan_off_on_exit_all_fans(mocker):
    ir1 = wrap_ir_backend(FakeIRBackend())
    ir2 = wrap_ir_backend(FakeIRBackend())
    unit1 = FanUnit(
        spec=FanSpec(id="fan1", firebase_node="fans/fan1", local=LocalFanConfig()),
        sensor_be=FakeSensorBackend(),
        ir_be=ir1,
    )
    unit2 = FanUnit(
        spec=FanSpec(id="fan2", firebase_node="fans/fan2", local=LocalFanConfig()),
        sensor_be=FakeSensorBackend(),
        ir_be=ir2,
    )

    mocker.patch("maxxair_fan.main.acquire_single_instance_lock", return_value=True)
    mocker.patch("maxxair_fan.main.release_single_instance_lock")
    mocker.patch("maxxair_fan.main.config.configure_logging")
    mocker.patch(
        "maxxair_fan.main.run_multi_fan_iteration",
        side_effect=lambda *_a, **_k: main.request_shutdown(),
    )
    mocker.patch("maxxair_fan.main.time.sleep")
    mocker.patch.object(config, "FAN_OFF_ON_EXIT", True)

    main.main(
        use_lock=False,
        skip_preflight=True,
        fb_be=InMemoryFirebaseBackend(),
        fan_units=[unit1, unit2],
    )

    assert ir1.inner.sent == ["fan_off.ir"]  # type: ignore[attr-defined]
    assert ir2.inner.sent == ["fan_off.ir"]  # type: ignore[attr-defined]


def test_load_fans_config_from_fixture(tmp_path, monkeypatch):
    fixture = tmp_path / "fans.json"
    fixture.write_text(
        '{"fans": [{"id": "fan1", "firebase_node": "fans/fan1", "local": {}}]}'
    )
    monkeypatch.setattr(config, "FANS_CONFIG", str(fixture))
    specs = load_fans_config()
    assert len(specs) == 1
    assert specs[0].id == "fan1"


def test_build_fan_unit_local():
    spec = FanSpec(
        id="fan1",
        firebase_node="fans/fan1",
        local=LocalFanConfig(sensor_path="/sys/s", ir_device="/dev/lirc1"),
    )
    unit = build_fan_unit(spec, fake_sensor=FakeSensorBackend(), fake_ir=FakeIRBackend())
    assert unit.spec.id == "fan1"
