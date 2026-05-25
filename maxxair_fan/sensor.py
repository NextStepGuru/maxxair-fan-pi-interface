import glob
import logging
import time
from pathlib import Path

from maxxair_fan import config

logger = logging.getLogger(__name__)

_resolved_sensor_path: Path | None = None
sensor_crc_failures = 0


def reset_sensor_stats() -> None:
    """Reset CRC failure counter (for tests)."""
    global sensor_crc_failures
    sensor_crc_failures = 0


def _discover_sensor_path() -> Path | None:
    candidates = sorted(glob.glob("/sys/bus/w1/devices/28-*/w1_slave"))
    if not candidates:
        logger.warning("No DS18B20 sensors found under /sys/bus/w1/devices/28-*")
        return None

    chosen = Path(candidates[0])
    if len(candidates) > 1:
        logger.warning(
            "Multiple DS18B20 sensors found; using %s (set SENSOR_PATH to override)",
            chosen,
        )
    else:
        logger.info("Auto-detected DS18B20 sensor at %s", chosen)

    return chosen


def get_sensor_path() -> Path | None:
    global _resolved_sensor_path

    if _resolved_sensor_path is not None:
        return _resolved_sensor_path

    if config.SENSOR_PATH_OVERRIDE:
        _resolved_sensor_path = Path(config.SENSOR_PATH_OVERRIDE)
        logger.info("Using sensor from SENSOR_PATH: %s", _resolved_sensor_path)
        return _resolved_sensor_path

    _resolved_sensor_path = _discover_sensor_path()
    return _resolved_sensor_path


def reset_sensor_path_cache() -> None:
    """Clear cached sensor path (for tests)."""
    global _resolved_sensor_path
    _resolved_sensor_path = None


def parse_w1_slave_content(content: str) -> float | None:
    """Parse DS18B20 w1_slave file content and return temperature in °F."""
    lines = content.splitlines()
    if len(lines) < 2:
        return None

    if "YES" not in lines[0]:
        logger.warning("DS18B20 CRC check failed")
        return None

    temp_str = lines[1].split("t=")[-1].strip()
    temp_c = float(temp_str) / 1000.0
    return temp_c * 9.0 / 5.0 + 32.0


def read_temp_f(sensor_path: Path | None = None, max_retries: int = 2) -> float | None:
    """Read DS18B20 temperature via kernel 1-wire interface."""
    global sensor_crc_failures

    path = sensor_path or get_sensor_path()
    if path is None:
        return None

    for attempt in range(max_retries + 1):
        try:
            content = path.read_text()
        except OSError as exc:
            logger.warning("Failed to read sensor at %s: %s", path, exc)
            return None

        lines = content.splitlines()
        if lines and "NO" in lines[0]:
            sensor_crc_failures += 1

        temp = parse_w1_slave_content(content)
        if temp is not None:
            return temp

        if attempt < max_retries:
            time.sleep(0.05)

    return None
