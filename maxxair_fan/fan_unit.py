"""Per-fan control unit extracted from the main control loop."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from maxxair_fan import config, fan
from maxxair_fan.backends.deduping_ir import DedupingIRBackend
from maxxair_fan.backends.protocols import FirebaseBackend, IRBackend, SensorBackend
from maxxair_fan.fans_config import FanSpec

logger = logging.getLogger(__name__)


@dataclass
class FanState:
    cached_target_temp: float = 72.0
    cached_direction: str = "in"
    last_patched_temp: float | None = None
    last_patch_time: float | None = None
    sensor_crc_failures: int = 0


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


def build_status_patch(
    *,
    now_iso: str,
    current_temp: float | None,
    sensor_ok: bool,
    ir_ok: bool,
    last_ir_command: str | None,
    last_error: str | None,
    sensor_crc_failures: int = 0,
) -> dict:
    patch = {
        "lastUpdate": now_iso,
        "online": True,
        "sensorOk": sensor_ok,
        "irOk": ir_ok,
        "lastIrCommand": last_ir_command,
        "lastError": last_error,
        "sensorCrcFailures": sensor_crc_failures,
    }
    if current_temp is not None:
        patch["currentTemp"] = current_temp
    return patch


def _ir_last_sent(ir_be: IRBackend) -> str | None:
    if isinstance(ir_be, DedupingIRBackend):
        return ir_be.last_sent
    return None


@dataclass
class FanUnit:
    spec: FanSpec
    sensor_be: SensorBackend
    ir_be: IRBackend
    state: FanState = field(default_factory=FanState)

    @property
    def fan_id(self) -> str:
        return self.spec.id

    @property
    def firebase_node(self) -> str:
        return self.spec.firebase_node

    def run_iteration(
        self,
        fb_be: FirebaseBackend,
        now: float,
        on_iteration: Callable[[dict], None] | None = None,
    ) -> FanState:
        now_iso = datetime.fromtimestamp(now, tz=UTC).isoformat()
        iteration_state: dict = {
            "fan_id": self.spec.id,
            "firebase_node": self.spec.firebase_node,
            "current_temp": None,
            "target_temp": self.state.cached_target_temp,
            "direction": self.state.cached_direction,
            "speed": 0,
            "ir_filename": None,
            "ir_sent": False,
            "patched": False,
            "patch_reason": "skipped",
        }

        data = fb_be.get(self.spec.firebase_node)
        if isinstance(data, dict):
            if "targetTemp" in data:
                try:
                    self.state.cached_target_temp = float(data["targetTemp"])
                    iteration_state["target_temp"] = self.state.cached_target_temp
                except (TypeError, ValueError):
                    logger.warning(
                        "Invalid targetTemp for %s: %r",
                        self.spec.id,
                        data["targetTemp"],
                    )

            if "direction" in data and data["direction"] in ("in", "out"):
                self.state.cached_direction = data["direction"]
                iteration_state["direction"] = self.state.cached_direction

        current_temp = self.sensor_be.read_temp_f()
        iteration_state["current_temp"] = current_temp

        last_ir_command = _ir_last_sent(self.ir_be)
        ir_ok = True
        last_error: str | None = None

        if current_temp is not None:
            speed = fan.compute_speed(current_temp, self.state.cached_target_temp)
            filename = fan.resolve_ir_filename(self.state.cached_direction, speed)
            iteration_state["speed"] = speed
            iteration_state["ir_filename"] = filename

            sent = self.ir_be.send(filename)
            iteration_state["ir_sent"] = sent and filename != last_ir_command
            ir_ok = sent
            if not sent:
                last_error = f"IR send failed for {filename}"
            last_ir_command = _ir_last_sent(self.ir_be)

            if should_patch_firebase(
                self.state.last_patched_temp,
                current_temp,
                self.state.last_patch_time,
                now,
            ):
                iteration_state["patch_reason"] = "updated"
                if fb_be.patch(
                    self.spec.firebase_node,
                    build_status_patch(
                        now_iso=now_iso,
                        current_temp=current_temp,
                        sensor_ok=True,
                        ir_ok=ir_ok,
                        last_ir_command=last_ir_command,
                        last_error=last_error,
                        sensor_crc_failures=self.state.sensor_crc_failures,
                    ),
                ):
                    self.state.last_patched_temp = current_temp
                    self.state.last_patch_time = now
                    iteration_state["patched"] = True
            else:
                iteration_state["patch_reason"] = "throttled"
        elif should_patch_status(self.state.last_patch_time, now):
            iteration_state["patch_reason"] = "sensor_failure"
            last_error = "Temperature read failed"
            if fb_be.patch(
                self.spec.firebase_node,
                build_status_patch(
                    now_iso=now_iso,
                    current_temp=None,
                    sensor_ok=False,
                    ir_ok=ir_ok,
                    last_ir_command=last_ir_command,
                    last_error=last_error,
                    sensor_crc_failures=self.state.sensor_crc_failures,
                ),
            ):
                self.state.last_patch_time = now
                iteration_state["patched"] = True

        if on_iteration is not None:
            on_iteration(iteration_state)

        return self.state
