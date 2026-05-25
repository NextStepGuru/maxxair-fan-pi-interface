"""Replay fixture runner for local simulation and tests."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from maxxair_fan import main
from maxxair_fan.backends import (
    DedupingIRBackend,
    FakeIRBackend,
    FakeSensorBackend,
    FirebaseBackend,
    InMemoryFirebaseBackend,
    IRBackend,
    wrap_ir_backend,
)


def parse_fixture_steps(steps: list[dict[str, Any]]) -> list[float | None]:
    temps: list[float | None] = []
    for step in steps:
        raw = step.get("temp")
        if raw is None:
            temps.append(None)
        else:
            temps.append(float(raw))
    return temps


def build_change_map(changes: list[dict[str, Any]], key: str) -> dict[int, Any]:
    return {int(change["after_step"]): change[key] for change in changes}


def run_replay_fixture(
    fixture: dict[str, Any],
    *,
    ir_be: IRBackend | None = None,
    fb_be: FirebaseBackend | None = None,
    start_now: float = 1000.0,
    step_seconds: float = 1.0,
    on_iteration: Callable[[dict], None] | None = None,
) -> tuple[list[str], FirebaseBackend]:
    """Run a replay fixture and return IR commands sent plus the Firebase backend."""
    target = float(fixture.get("target", 72.0))
    direction = fixture.get("direction", "in")
    temps = parse_fixture_steps(fixture.get("steps", []))
    direction_changes = build_change_map(fixture.get("direction_changes", []), "direction")
    target_changes = build_change_map(fixture.get("target_changes", []), "target")

    sensor = FakeSensorBackend(series=temps)
    fake_ir = FakeIRBackend()
    if ir_be is None:
        ir_be = wrap_ir_backend(fake_ir)

    memory_fb = fb_be or InMemoryFirebaseBackend(
        {"fans": {"fan1": {"targetTemp": target, "direction": direction}}}
    )

    cached_target = target
    cached_direction = direction
    last_temp: float | None = None
    last_time: float | None = None
    now = start_now

    for index in range(len(temps)):
        patches: dict[str, Any] = {}
        if index in direction_changes:
            patches["direction"] = direction_changes[index]
        if index in target_changes:
            patches["targetTemp"] = float(target_changes[index])
        if patches:
            memory_fb.patch("fans/fan1", patches)

        cached_target, cached_direction, last_temp, last_time = main.run_loop_iteration(
            cached_target,
            cached_direction,
            last_temp,
            last_time,
            sensor_be=sensor,
            ir_be=ir_be,
            fb_be=memory_fb,
            now=now,
            on_iteration=on_iteration,
        )
        now += step_seconds

    if isinstance(ir_be, DedupingIRBackend):
        inner = ir_be.inner
        if isinstance(inner, FakeIRBackend):
            return inner.sent, memory_fb

    if isinstance(ir_be, FakeIRBackend):
        return ir_be.sent, memory_fb

    raise TypeError("run_replay_fixture requires FakeIRBackend or DedupingIRBackend wrapping it")


def run_replay_fixture_path(path: Path | str) -> tuple[list[str], FirebaseBackend]:
    fixture = json.loads(Path(path).read_text())
    return run_replay_fixture(fixture)


def load_expected_ir(fixture: dict[str, Any]) -> list[str] | None:
    expected = fixture.get("expected_ir")
    if expected is None:
        return None
    return list(expected)
