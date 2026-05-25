import fcntl
import logging
import shutil
import signal
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from maxxair_fan import config, fan, sensor
from maxxair_fan.backends import build_backends, wrap_ir_backend
from maxxair_fan.backends.deduping_ir import DedupingIRBackend
from maxxair_fan.backends.protocols import FirebaseBackend, IRBackend, SensorBackend

logger = logging.getLogger(__name__)

# Module-level daemon state (single process, single instance lock).
_shutdown_requested = False
_lock_file_handle = None


def request_shutdown(signum=None, frame=None) -> None:
    global _shutdown_requested
    _shutdown_requested = True
    logger.info("Shutdown requested (signal=%s)", signum)


def is_shutdown_requested() -> bool:
    return _shutdown_requested


def reset_shutdown_flag() -> None:
    """Reset shutdown flag (for tests)."""
    global _shutdown_requested
    _shutdown_requested = False


def should_patch_firebase(
    last_patched_temp: float | None,
    current_temp: float,
    last_patch_time: float | None,
    now: float,
) -> bool:
    if last_patched_temp is None:
        return True

    if abs(current_temp - last_patched_temp) >= config.TEMP_PATCH_THRESHOLD:
        return True

    if last_patch_time is None:
        return True

    return (now - last_patch_time) >= config.PATCH_HEARTBEAT_SECONDS


def should_patch_status(last_patch_time: float | None, now: float) -> bool:
    if last_patch_time is None:
        return True
    return (now - last_patch_time) >= config.PATCH_HEARTBEAT_SECONDS


def _ir_last_sent(ir_be: IRBackend) -> str | None:
    if isinstance(ir_be, DedupingIRBackend):
        return ir_be.last_sent
    return None


def build_status_patch(
    *,
    now_iso: str,
    current_temp: float | None,
    sensor_ok: bool,
    ir_ok: bool,
    last_ir_command: str | None,
    last_error: str | None,
) -> dict:
    patch = {
        "lastUpdate": now_iso,
        "online": True,
        "sensorOk": sensor_ok,
        "irOk": ir_ok,
        "lastIrCommand": last_ir_command,
        "lastError": last_error,
        "sensorCrcFailures": sensor.sensor_crc_failures,
    }
    if current_temp is not None:
        patch["currentTemp"] = current_temp
    return patch


def validate_runtime(fb_be: FirebaseBackend | None = None) -> list[str]:
    """Return a list of preflight errors (empty if ready to run on Pi hardware)."""
    if config.MAXXAIR_BACKEND == "simulator":
        return []

    if config.MAXXAIR_SKIP_PREFLIGHT:
        return []

    errors: list[str] = []

    firebase_name = config.FIREBASE_BACKEND or (
        "memory" if config.MAXXAIR_BACKEND == "simulator" else "rest"
    )
    if firebase_name == "rest" and not config.FIREBASE_URL:
        errors.append("FIREBASE_URL is not set")

    if shutil.which("ir-ctl") is None:
        errors.append("ir-ctl not found on PATH (install v4l-utils)")

    if not config.IR_DIR.exists():
        errors.append(f"IR_DIR does not exist: {config.IR_DIR}")
    elif not (config.IR_DIR / "fan_off.ir").exists():
        errors.append(f"fan_off.ir missing from IR_DIR: {config.IR_DIR}")

    sensor_path = sensor.get_sensor_path()
    if sensor_path is None:
        errors.append("No DS18B20 sensor found (enable 1-wire or set SENSOR_PATH)")

    if firebase_name == "rest" and config.FIREBASE_URL and fb_be is not None:
        probe = fb_be.get(config.FAN_NODE)
        if probe is None and config.FIREBASE_URL:
            errors.append(f"Firebase GET failed for {config.FAN_NODE}")

    return errors


def acquire_single_instance_lock(lock_file: Path | None = None) -> bool:
    global _lock_file_handle

    path = lock_file or config.LOCK_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    handle = open(path, "w")  # noqa: SIM115 — lock must stay open for process lifetime
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        logger.error("Another maxxair-fan instance is already running (lock: %s)", path)
        return False

    handle.write(str(Path(__file__).resolve().parent.parent))
    handle.flush()
    _lock_file_handle = handle
    logger.info("Acquired instance lock at %s", path)
    return True


def release_single_instance_lock() -> None:
    global _lock_file_handle

    if _lock_file_handle is None:
        return

    try:
        fcntl.flock(_lock_file_handle.fileno(), fcntl.LOCK_UN)
        _lock_file_handle.close()
    except OSError:
        pass
    finally:
        _lock_file_handle = None


def run_loop_iteration(
    cached_target_temp: float,
    cached_direction: str,
    last_patched_temp: float | None,
    last_patch_time: float | None,
    sensor_be: SensorBackend | None = None,
    ir_be: IRBackend | None = None,
    fb_be: FirebaseBackend | None = None,
    on_iteration: Callable[[dict], None] | None = None,
    now: float | None = None,
) -> tuple[float, str, float | None, float | None]:
    """Run one control-loop iteration. Returns updated cache state."""
    if sensor_be is None or ir_be is None or fb_be is None:
        default_sensor, default_ir, default_fb = build_backends()
        sensor_be = sensor_be or default_sensor
        ir_be = ir_be or default_ir
        fb_be = fb_be or default_fb

    current_now = now if now is not None else time.time()
    now_iso = datetime.fromtimestamp(current_now, tz=UTC).isoformat()
    iteration_state: dict = {
        "current_temp": None,
        "target_temp": cached_target_temp,
        "direction": cached_direction,
        "speed": 0,
        "ir_filename": None,
        "ir_sent": False,
        "patched": False,
        "patch_reason": "skipped",
    }

    data = fb_be.get(config.FAN_NODE)
    if isinstance(data, dict):
        if "targetTemp" in data:
            try:
                cached_target_temp = float(data["targetTemp"])
                iteration_state["target_temp"] = cached_target_temp
            except (TypeError, ValueError):
                logger.warning("Invalid targetTemp in Firebase: %r", data["targetTemp"])

        if "direction" in data and data["direction"] in ("in", "out"):
            cached_direction = data["direction"]
            iteration_state["direction"] = cached_direction

    current_temp = sensor_be.read_temp_f()
    iteration_state["current_temp"] = current_temp

    last_ir_command = _ir_last_sent(ir_be)
    ir_ok = True
    last_error: str | None = None

    if current_temp is not None:
        speed = fan.compute_speed(current_temp, cached_target_temp)
        filename = fan.resolve_ir_filename(cached_direction, speed)
        iteration_state["speed"] = speed
        iteration_state["ir_filename"] = filename

        sent = ir_be.send(filename)
        iteration_state["ir_sent"] = sent and filename != last_ir_command
        ir_ok = sent
        if not sent:
            last_error = f"IR send failed for {filename}"
        last_ir_command = _ir_last_sent(ir_be)

        if should_patch_firebase(last_patched_temp, current_temp, last_patch_time, current_now):
            iteration_state["patch_reason"] = "updated"
            if fb_be.patch(
                config.FAN_NODE,
                build_status_patch(
                    now_iso=now_iso,
                    current_temp=current_temp,
                    sensor_ok=True,
                    ir_ok=ir_ok,
                    last_ir_command=last_ir_command,
                    last_error=last_error,
                ),
            ):
                last_patched_temp = current_temp
                last_patch_time = current_now
                iteration_state["patched"] = True
        else:
            iteration_state["patch_reason"] = "throttled"
    elif should_patch_status(last_patch_time, current_now):
        iteration_state["patch_reason"] = "sensor_failure"
        last_error = "DS18B20 read failed"
        if fb_be.patch(
            config.FAN_NODE,
            build_status_patch(
                now_iso=now_iso,
                current_temp=None,
                sensor_ok=False,
                ir_ok=ir_ok,
                last_ir_command=last_ir_command,
                last_error=last_error,
            ),
        ):
            last_patch_time = current_now
            iteration_state["patched"] = True

    if on_iteration is not None:
        on_iteration(iteration_state)

    return cached_target_temp, cached_direction, last_patched_temp, last_patch_time


def main(
    *,
    once: bool = False,
    use_lock: bool = True,
    skip_preflight: bool = False,
    sensor_be: SensorBackend | None = None,
    ir_be: IRBackend | None = None,
    fb_be: FirebaseBackend | None = None,
    on_iteration: Callable[[dict], None] | None = None,
) -> None:
    config.configure_logging()
    logger.info("Starting MaxxAir fan controller (backend=%s)", config.MAXXAIR_BACKEND)

    if sensor_be is None or ir_be is None or fb_be is None:
        built_sensor, built_ir, built_fb = build_backends()
        sensor_be = sensor_be or built_sensor
        ir_be = ir_be or built_ir
        fb_be = fb_be or built_fb

    if not skip_preflight and config.MAXXAIR_BACKEND != "simulator":
        errors = validate_runtime(fb_be)
        if errors:
            for error in errors:
                logger.error("Preflight failed: %s", error)
            sys.exit(1)

    if use_lock and not acquire_single_instance_lock():
        sys.exit(1)

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)

    cached_target_temp = 72.0
    cached_direction = "in"
    last_patched_temp: float | None = None
    last_patch_time: float | None = None

    try:
        while not is_shutdown_requested():
            (
                cached_target_temp,
                cached_direction,
                last_patched_temp,
                last_patch_time,
            ) = run_loop_iteration(
                cached_target_temp,
                cached_direction,
                last_patched_temp,
                last_patch_time,
                sensor_be=sensor_be,
                ir_be=ir_be,
                fb_be=fb_be,
                on_iteration=on_iteration,
            )
            if once:
                break
            time.sleep(config.CHECK_INTERVAL)
    finally:
        if config.FAN_OFF_ON_EXIT:
            logger.info("Sending fan_off on exit")
            wrap_ir_backend(ir_be).send("fan_off.ir")

        if use_lock:
            release_single_instance_lock()
        logger.info("MaxxAir fan controller stopped")
