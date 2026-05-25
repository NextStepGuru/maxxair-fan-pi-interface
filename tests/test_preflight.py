from maxxair_fan import config, main
from maxxair_fan.backends import InMemoryFirebaseBackend


def test_validate_runtime_simulator_mode(monkeypatch):
    monkeypatch.setattr(config, "MAXXAIR_BACKEND", "simulator")
    assert main.validate_runtime() == []


def test_validate_runtime_skip_flag(monkeypatch):
    monkeypatch.setattr(config, "MAXXAIR_BACKEND", "pi")
    monkeypatch.setattr(config, "MAXXAIR_SKIP_PREFLIGHT", True)
    assert main.validate_runtime() == []


def test_validate_runtime_missing_firebase(monkeypatch):
    monkeypatch.setattr(config, "MAXXAIR_BACKEND", "pi")
    monkeypatch.setattr(config, "MAXXAIR_SKIP_PREFLIGHT", False)
    monkeypatch.setattr(config, "FIREBASE_BACKEND", "rest")
    monkeypatch.setattr(config, "FIREBASE_URL", "")
    monkeypatch.setattr(config, "IR_DIR", config.REPO_ROOT / "ir_codes")

    errors = main.validate_runtime(InMemoryFirebaseBackend())
    assert any("FIREBASE_URL" in error for error in errors)


def test_build_status_patch_includes_telemetry_fields():
    patch = main.build_status_patch(
        now_iso="2026-01-01T00:00:00+00:00",
        current_temp=73.0,
        sensor_ok=True,
        ir_ok=True,
        last_ir_command="fan_on_in_40.ir",
        last_error=None,
    )
    assert patch["online"] is True
    assert patch["sensorOk"] is True
    assert patch["lastIrCommand"] == "fan_on_in_40.ir"
    assert patch["currentTemp"] == 73.0


def test_validate_runtime_missing_ir_ctl(monkeypatch, mocker):
    monkeypatch.setattr(config, "MAXXAIR_BACKEND", "pi")
    monkeypatch.setattr(config, "MAXXAIR_SKIP_PREFLIGHT", False)
    monkeypatch.setattr(config, "FIREBASE_BACKEND", "memory")
    monkeypatch.setattr(config, "FIREBASE_URL", "http://example.test")
    monkeypatch.setattr(config, "IR_DIR", config.REPO_ROOT / "ir_codes")
    mocker.patch("shutil.which", return_value=None)
    mocker.patch("maxxair_fan.main.sensor.get_sensor_path", return_value="/sys/bus/w1/0")

    errors = main.validate_runtime(InMemoryFirebaseBackend())
    assert any("ir-ctl" in error for error in errors)


def test_validate_runtime_remote_agent_failure(monkeypatch, mocker):
    monkeypatch.setattr(config, "MAXXAIR_BACKEND", "pi")
    monkeypatch.setattr(config, "MAXXAIR_SKIP_PREFLIGHT", False)
    monkeypatch.setattr(config, "FIREBASE_BACKEND", "memory")
    monkeypatch.setattr(config, "FIREBASE_URL", "http://example.test")
    monkeypatch.setattr(config, "IR_DIR", config.REPO_ROOT / "ir_codes")
    mocker.patch("shutil.which", return_value="/usr/bin/ir-ctl")

    from maxxair_fan.backends.remote_agent import RemoteAgentBackend
    from maxxair_fan.fan_unit import FanUnit
    from maxxair_fan.fans_config import FanSpec

    remote = RemoteAgentBackend("http://unreachable-agent")
    mocker.patch.object(remote, "health_check", return_value=False)
    unit = FanUnit(
        spec=FanSpec(id="fan2", firebase_node="fans/fan2", agent_url="http://unreachable-agent"),
        sensor_be=remote,
        ir_be=remote,
    )

    errors = main.validate_runtime(InMemoryFirebaseBackend(), [unit])
    assert any("agent health check failed" in error for error in errors)


def test_validate_runtime_missing_sensor(monkeypatch, mocker):
    monkeypatch.setattr(config, "MAXXAIR_BACKEND", "pi")
    monkeypatch.setattr(config, "MAXXAIR_SKIP_PREFLIGHT", False)
    monkeypatch.setattr(config, "FIREBASE_BACKEND", "memory")
    monkeypatch.setattr(config, "FIREBASE_URL", "http://example.test")
    monkeypatch.setattr(config, "IR_DIR", config.REPO_ROOT / "ir_codes")
    mocker.patch("shutil.which", return_value="/usr/bin/ir-ctl")
    mocker.patch("maxxair_fan.main.sensor.get_sensor_path", return_value=None)

    errors = main.validate_runtime(InMemoryFirebaseBackend())
    assert any("DS18B20" in error for error in errors)
