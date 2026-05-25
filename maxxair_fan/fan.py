import logging
import math
import subprocess

from maxxair_fan import config

logger = logging.getLogger(__name__)


def resolve_ir_filename(direction: str, speed: int) -> str:
    if speed == 0:
        return "fan_off.ir"

    if direction == "out":
        return f"fan_on_out_{speed}.ir"

    return f"fan_on_in_{speed}.ir"


def send_ir(filename: str) -> bool:
    """Send IR signal file with ir-ctl. Returns True on success."""
    ir_path = config.IR_DIR / filename
    if not ir_path.exists():
        logger.error("IR file not found: %s", ir_path)
        return False

    try:
        subprocess.run(
            ["ir-ctl", "-s", str(ir_path)],
            check=True,
            timeout=5,
        )
        return True
    except (subprocess.SubprocessError, OSError) as exc:
        logger.error("IR send failed for %s: %s", filename, exc)
        return False


def compute_speed(
    current_temp: float,
    target_temp: float,
    gradient_degrees: float | None = None,
    exponent_value: float | None = None,
) -> int:
    diff = current_temp - target_temp
    if diff <= 0:
        return 0

    gradient = gradient_degrees if gradient_degrees is not None else config.GRADIENT_DEGREES
    exponent = exponent_value if exponent_value is not None else config.EXPONENT_VALUE

    units_above = diff / gradient
    speed = 10.0 * math.pow(exponent, units_above - 1)

    if speed > 100:
        speed = 100

    speed = int(round(speed / 10.0)) * 10
    return max(0, min(speed, 100))
