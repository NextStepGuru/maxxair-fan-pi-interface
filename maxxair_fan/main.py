import fcntl
import logging
import shutil
import signal
import sys
import time
from collections.abc import Callable
from pathlib import Path

from maxxair_fan import config, sensor
from maxxair_fan.backends import build_backends, load_fan_units
from maxxair_fan.backends.protocols import FirebaseBackend, IRBackend, SensorBackend
from maxxair_fan.backends.remote_agent import RemoteAgentBackend
from maxxair_fan.fan_unit import (
    FanState,
    FanUnit,
    should_patch_firebase,
    should_patch_status,
)
from maxxair_fan.fan_unit import (
    build_status_patch as _build_status_patch,
)
from maxxair_fan.fans_config import legacy_fan_spec

logger = logging.getLogger(__name__)

__all__ = [
    "acquire_single_instance_lock",
    "build_status_patch",
    "is_shutdown_requested",
    "main",
    "release_single_instance_lock",
    "request_shutdown",
    "reset_shutdown_flag",
    "run_loop_iteration",
    "run_multi_fan_iteration",
    "should_patch_firebase",
    "should_patch_status",
    "validate_runtime",
]

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


def build_status_patch(
    *,
    now_iso: str,
    current_temp: float | None,
    sensor_ok: bool,
    ir_ok: bool,
    last_ir_command: str | None,
    last_error: str | None,
    sensor_crc_failures: int | None = None,
) -> dict:
    if sensor_crc_failures is None:
        sensor_crc_failures = sensor.sensor_crc_failures
    return _build_status_patch(
        now_iso=now_iso,
        current_temp=current_temp,
        sensor_ok=sensor_ok,
        ir_ok=ir_ok,
        last_ir_command=last_ir_command,
        last_error=last_error,
        sensor_crc_failures=sensor_crc_failures,
    )


def validate_runtime(
    fb_be: FirebaseBackend | None = None,
    fan_units: list[FanUnit] | None = None,
) -> list[str]:
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

    if fan_units is None:
        try:
            fan_units = load_fan_units()
        except (FileNotFoundError, ValueError) as exc:
            errors.append(str(exc))
            return errors

    has_local = any(unit.spec.is_local for unit in fan_units)

    if has_local and shutil.which("ir-ctl") is None:
        errors.append("ir-ctl not found on PATH (install v4l-utils)")

    if not config.IR_DIR.exists():
        errors.append(f"IR_DIR does not exist: {config.IR_DIR}")
    elif not (config.IR_DIR / "fan_off.ir").exists():
        errors.append(f"fan_off.ir missing from IR_DIR: {config.IR_DIR}")

    for unit in fan_units:
        if unit.spec.is_local:
            local = unit.spec.local
            if local and local.sensor_path:
                sensor_path = Path(local.sensor_path)
                if not sensor_path.exists():
                    errors.append(
                        f"Fan {unit.spec.id}: sensor path not found: {local.sensor_path}"
                    )
            elif len([u for u in fan_units if u.spec.is_local]) == 1:
                if sensor.get_sensor_path() is None:
                    errors.append(
                        f"Fan {unit.spec.id}: no DS18B20 sensor found "
                        "(enable 1-wire or set sensor_path)"
                    )
            else:
                errors.append(
                    f"Fan {unit.spec.id}: sensor_path required when multiple local fans"
                )
        else:
            remote = unit.sensor_be
            if isinstance(remote, RemoteAgentBackend) and not remote.health_check():
                errors.append(
                    f"Fan {unit.spec.id}: agent health check failed "
                    f"({unit.spec.agent_url})"
                )

        if firebase_name == "rest" and config.FIREBASE_URL and fb_be is not None:
            probe = fb_be.get(unit.spec.firebase_node)
            if probe is None:
                errors.append(f"Firebase GET failed for {unit.spec.firebase_node}")

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
    """Run one control-loop iteration for the legacy single-fan API."""
    if sensor_be is None or ir_be is None or fb_be is None:
        default_sensor, default_ir, default_fb = build_backends()
        sensor_be = sensor_be or default_sensor
        ir_be = ir_be or default_ir
        fb_be = fb_be or default_fb

    current_now = now if now is not None else time.time()
    unit = FanUnit(
        spec=legacy_fan_spec(),
        sensor_be=sensor_be,
        ir_be=ir_be,
        state=FanState(
            cached_target_temp=cached_target_temp,
            cached_direction=cached_direction,
            last_patched_temp=last_patched_temp,
            last_patch_time=last_patch_time,
            sensor_crc_failures=sensor.sensor_crc_failures,
        ),
    )
    state = unit.run_iteration(fb_be, current_now, on_iteration)
    return (
        state.cached_target_temp,
        state.cached_direction,
        state.last_patched_temp,
        state.last_patch_time,
    )


def run_multi_fan_iteration(
    fan_units: list[FanUnit],
    fb_be: FirebaseBackend,
    on_iteration: Callable[[dict], None] | None = None,
    now: float | None = None,
) -> None:
    """Run one control-loop iteration for all configured fans."""
    current_now = now if now is not None else time.time()
    for unit in fan_units:
        unit.run_iteration(fb_be, current_now, on_iteration)


def main(
    *,
    once: bool = False,
    use_lock: bool = True,
    skip_preflight: bool = False,
    sensor_be: SensorBackend | None = None,
    ir_be: IRBackend | None = None,
    fb_be: FirebaseBackend | None = None,
    fan_units: list[FanUnit] | None = None,
    on_iteration: Callable[[dict], None] | None = None,
) -> None:
    config.configure_logging()
    logger.info("Starting MaxxAir fan controller (backend=%s)", config.MAXXAIR_BACKEND)

    if fan_units is None:
        if sensor_be is not None or ir_be is not None:
            if sensor_be is None or ir_be is None or fb_be is None:
                built_sensor, built_ir, built_fb = build_backends()
                sensor_be = sensor_be or built_sensor
                ir_be = ir_be or built_ir
                fb_be = fb_be or built_fb
            fan_units = [
                FanUnit(
                    spec=legacy_fan_spec(),
                    sensor_be=sensor_be,
                    ir_be=ir_be,
                )
            ]
        else:
            _, _, built_fb = build_backends()
            fb_be = fb_be or built_fb
            fan_units = load_fan_units()
    else:
        if fb_be is None:
            _, _, fb_be = build_backends()

    if fb_be is None:
        _, _, fb_be = build_backends()

    fan_ids = ", ".join(unit.spec.id for unit in fan_units)
    logger.info("Controlling %d fan(s): %s", len(fan_units), fan_ids)

    if not skip_preflight and config.MAXXAIR_BACKEND != "simulator":
        errors = validate_runtime(fb_be, fan_units)
        if errors:
            for error in errors:
                logger.error("Preflight failed: %s", error)
            sys.exit(1)

    if use_lock and not acquire_single_instance_lock():
        sys.exit(1)

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)

    try:
        while not is_shutdown_requested():
            run_multi_fan_iteration(
                fan_units,
                fb_be,
                on_iteration=on_iteration,
            )
            if once:
                break
            time.sleep(config.CHECK_INTERVAL)
    finally:
        if config.FAN_OFF_ON_EXIT:
            logger.info("Sending fan_off on exit for all fans")
            for unit in fan_units:
                unit.ir_be.send("fan_off.ir")

        if use_lock:
            release_single_instance_lock()
        logger.info("MaxxAir fan controller stopped")
