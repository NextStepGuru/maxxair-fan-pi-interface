from pathlib import Path

import pytest

from maxxair_fan import sensor

VALID_W1_SLAVE = "a5 01 4b 46 7f ff 0c 10 5d : crc=5d YES\na5 01 4b 46 7f ff 0c 10 5d t=21875\n"

INVALID_CRC_W1_SLAVE = (
    "a5 01 4b 46 7f ff 0c 10 5d : crc=5d NO\na5 01 4b 46 7f ff 0c 10 5d t=21875\n"
)


@pytest.fixture(autouse=True)
def reset_stats():
    sensor.reset_sensor_stats()
    yield
    sensor.reset_sensor_stats()


def test_read_temp_f_retries_after_crc_fail(tmp_path):
    sensor_file = tmp_path / "w1_slave"
    writes = {"count": 0}

    def read_side_effect():
        writes["count"] += 1
        if writes["count"] == 1:
            return INVALID_CRC_W1_SLAVE
        return VALID_W1_SLAVE

    original_read_text = Path.read_text

    def patched_read_text(self, encoding=None):
        if self == sensor_file:
            return read_side_effect()
        return original_read_text(self, encoding=encoding)

    Path.read_text = patched_read_text  # type: ignore[method-assign]
    try:
        temp = sensor.read_temp_f(sensor_file, max_retries=2)
    finally:
        Path.read_text = original_read_text  # type: ignore[method-assign]

    assert temp == pytest.approx(71.375)
    assert sensor.sensor_crc_failures == 1


def test_read_temp_f_increments_crc_failures(tmp_path):
    sensor_file = tmp_path / "w1_slave"
    sensor_file.write_text(INVALID_CRC_W1_SLAVE)
    assert sensor.read_temp_f(sensor_file, max_retries=0) is None
    assert sensor.sensor_crc_failures == 1
