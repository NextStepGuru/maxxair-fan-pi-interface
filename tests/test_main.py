import time

import pytest

from maxxair_fan import config, main
from maxxair_fan.backends import (
    FakeIRBackend,
    FakeSensorBackend,
    InMemoryFirebaseBackend,
    wrap_ir_backend,
)


@pytest.fixture(autouse=True)
def reset_state():
    main.reset_shutdown_flag()
    yield
    main.reset_shutdown_flag()


@pytest.fixture
def fake_backends():
    sensor = FakeSensorBackend(temp=72.0)
    ir = wrap_ir_backend(FakeIRBackend())
    fb = InMemoryFirebaseBackend()
    yield sensor, ir, fb


def test_should_patch_firebase_first_read():
    assert main.should_patch_firebase(None, 72.0, None, time.time()) is True


def test_should_patch_firebase_temp_change(monkeypatch):
    monkeypatch.setattr(config, "TEMP_PATCH_THRESHOLD", 0.1)
    now = time.time()
    assert main.should_patch_firebase(72.0, 72.2, now, now) is True
    assert main.should_patch_firebase(72.0, 72.05, now, now) is False


def test_should_patch_firebase_heartbeat(monkeypatch):
    monkeypatch.setattr(config, "TEMP_PATCH_THRESHOLD", 0.1)
    monkeypatch.setattr(config, "PATCH_HEARTBEAT_SECONDS", 60)
    now = 1000.0
    assert main.should_patch_firebase(72.0, 72.0, now - 61, now) is True
    assert main.should_patch_firebase(72.0, 72.0, now - 30, now) is False


def test_run_loop_iteration_skips_when_sensor_fails(fake_backends):
    sensor_be, ir_be, fb_be = fake_backends

    class NullSensor(FakeSensorBackend):
        def read_temp_f(self):
            return None

    result = main.run_loop_iteration(
        72.0,
        "in",
        None,
        None,
        sensor_be=NullSensor(),
        ir_be=ir_be,
        fb_be=fb_be,
        now=1000.0,
    )

    assert result == (72.0, "in", None, 1000.0)
    assert ir_be.last_sent is None  # type: ignore[attr-defined]
    assert fb_be.get("fans/fan1")["sensorOk"] is False


def test_run_loop_iteration_controls_fan_and_patches(fake_backends):
    sensor_be, ir_be, fb_be = fake_backends
    inner_ir = ir_be.inner  # type: ignore[attr-defined]
    fb_be.put("fans/fan1", {"targetTemp": 70, "direction": "out"})
    sensor_be.set_temp(75.0)

    target, direction, last_temp, last_time = main.run_loop_iteration(
        72.0,
        "in",
        None,
        None,
        sensor_be=sensor_be,
        ir_be=ir_be,
        fb_be=fb_be,
        now=1000.0,
    )

    assert target == 70.0
    assert direction == "out"
    assert last_temp == 75.0
    assert last_time == 1000.0
    assert inner_ir.sent == ["fan_on_out_100.ir"]
    node = fb_be.get("fans/fan1")
    assert node["currentTemp"] == 75.0
    assert node["online"] is True
    assert node["sensorOk"] is True


def test_run_loop_iteration_ir_failure_sets_telemetry(fake_backends):
    sensor_be, _ir_be, fb_be = fake_backends
    sensor_be.set_temp(75.0)

    class FailingIR:
        def send(self, filename: str) -> bool:
            return False

    ir_be = wrap_ir_backend(FailingIR())

    main.run_loop_iteration(
        72.0,
        "in",
        None,
        None,
        sensor_be=sensor_be,
        ir_be=ir_be,
        fb_be=fb_be,
        now=1000.0,
    )

    node = fb_be.get("fans/fan1")
    assert node["irOk"] is False
    assert "IR send failed" in node["lastError"]


def test_run_loop_iteration_throttles_patch(fake_backends, monkeypatch):
    sensor_be, ir_be, fb_be = fake_backends
    sensor_be.set_temp(72.0)
    monkeypatch.setattr(config, "TEMP_PATCH_THRESHOLD", 0.1)
    monkeypatch.setattr(config, "PATCH_HEARTBEAT_SECONDS", 60)

    main.run_loop_iteration(
        72.0,
        "in",
        72.0,
        1000.0,
        sensor_be=sensor_be,
        ir_be=ir_be,
        fb_be=fb_be,
        now=1030.0,
    )

    assert "currentTemp" not in (fb_be.get("fans/fan1") or {})


def test_shutdown_flag():
    main.request_shutdown()
    assert main.is_shutdown_requested() is True
    main.reset_shutdown_flag()
    assert main.is_shutdown_requested() is False


def test_acquire_single_instance_lock(tmp_path, monkeypatch):
    lock_path = tmp_path / "test.lock"
    monkeypatch.setattr(config, "LOCK_FILE", lock_path)

    assert main.acquire_single_instance_lock(lock_path) is True
    main.release_single_instance_lock()

    assert main.acquire_single_instance_lock(lock_path) is True
    main.release_single_instance_lock()


def test_acquire_lock_fails_when_held(tmp_path, monkeypatch):
    lock_path = tmp_path / "held.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    import fcntl

    handle = open(lock_path, "w")  # noqa: SIM115
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    assert main.acquire_single_instance_lock(lock_path) is False
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    handle.close()


def test_main_runs_two_iterations_then_shuts_down(mocker):
    mocker.patch("maxxair_fan.main.acquire_single_instance_lock", return_value=True)
    mocker.patch("maxxair_fan.main.release_single_instance_lock")
    mocker.patch("maxxair_fan.main.config.configure_logging")
    mocker.patch.object(config, "FAN_OFF_ON_EXIT", False)
    mocker.patch.object(config, "CHECK_INTERVAL", 1)
    iteration = mocker.patch(
        "maxxair_fan.main.run_multi_fan_iteration",
    )
    sleep_calls = {"count": 0}

    def sleep_side_effect(_interval):
        sleep_calls["count"] += 1
        if sleep_calls["count"] >= 2:
            main.request_shutdown()

    mocker.patch("maxxair_fan.main.time.sleep", side_effect=sleep_side_effect)

    main.main(skip_preflight=True)

    assert iteration.call_count == 2


def test_main_fan_off_on_exit(mocker):
    fake_ir = wrap_ir_backend(FakeIRBackend())
    inner = fake_ir.inner
    mocker.patch("maxxair_fan.main.acquire_single_instance_lock", return_value=True)
    mocker.patch("maxxair_fan.main.release_single_instance_lock")
    mocker.patch(
        "maxxair_fan.main.run_multi_fan_iteration",
        side_effect=lambda *_a, **_k: main.request_shutdown(),
    )
    mocker.patch("maxxair_fan.main.time.sleep")
    mocker.patch("maxxair_fan.main.config.configure_logging")
    mocker.patch.object(config, "FAN_OFF_ON_EXIT", True)

    main.main(
        use_lock=False,
        skip_preflight=True,
        sensor_be=FakeSensorBackend(),
        ir_be=fake_ir,
        fb_be=InMemoryFirebaseBackend(),
    )

    assert inner.sent == ["fan_off.ir"]
