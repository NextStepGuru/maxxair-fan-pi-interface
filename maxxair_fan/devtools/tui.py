import sys
from typing import Any


def format_iteration_state(state: dict[str, Any]) -> str:
    current = state.get("current_temp")
    target = state.get("target_temp")
    direction = state.get("direction", "?")
    speed = state.get("speed", 0)
    filename = state.get("ir_filename") or "-"
    patch_reason = state.get("patch_reason", "?")

    if current is None:
        temp_part = "t=---"
        diff_part = "diff=---"
    else:
        temp_part = f"t={current:.1f}°F"
        diff = current - float(target)
        diff_part = f"diff={diff:+.1f}"

    return (
        f"{temp_part} target={float(target):.1f}°F {diff_part} "
        f"speed={speed}% dir={direction} cmd={filename} patch={patch_reason}"
    )


class LiveTUI:
    """Single-line live status output to stderr."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def __call__(self, state: dict[str, Any]) -> None:
        if not self.enabled:
            return
        line = format_iteration_state(state)
        sys.stderr.write(f"\r{line:<120}")
        sys.stderr.flush()

    def close(self) -> None:
        if self.enabled:
            sys.stderr.write("\n")
            sys.stderr.flush()
