from pathlib import Path

import pytest

from maxxair_fan import sensor

VALID_W1_SLAVE = "a5 01 4b 46 7f ff 0c 10 5d : crc=5d YES\na5 01 4b 46 7f ff 0c 10 5d t=21875\n"

INVALID_CRC_W1_SLAVE = (
    "a5 01 4b 46 7f ff 0c 10 5d : crc=5d NO\na5 01 4b 46 7f ff 0c 10 5d t=21875\n"
)


def test_parse_w1_slave_valid():
    # 21875 milli°C = 21.875°C = 71.375°F
    temp_f = sensor.parse_w1_slave_content(VALID_W1_SLAVE)
    assert temp_f == pytest.approx(71.375)


def test_parse_w1_slave_crc_fail():
    assert sensor.parse_w1_slave_content(INVALID_CRC_W1_SLAVE) is None


def test_parse_w1_slave_malformed():
    assert sensor.parse_w1_slave_content("only one line") is None


def test_read_temp_f_from_path(tmp_path):
    sensor_file = tmp_path / "w1_slave"
    sensor_file.write_text(VALID_W1_SLAVE)
    assert sensor.read_temp_f(sensor_file) == pytest.approx(71.375)


def test_read_temp_f_missing_file(tmp_path):
    assert sensor.read_temp_f(tmp_path / "missing") is None


def test_get_sensor_path_override(monkeypatch, tmp_path):
    sensor.reset_sensor_path_cache()
    sensor_file = tmp_path / "w1_slave"
    sensor_file.write_text(VALID_W1_SLAVE)
    monkeypatch.setenv("SENSOR_PATH", str(sensor_file))

    from maxxair_fan import config

    monkeypatch.setattr(config, "SENSOR_PATH_OVERRIDE", str(sensor_file))
    path = sensor.get_sensor_path()
    assert path == Path(sensor_file)
    sensor.reset_sensor_path_cache()


def test_discover_sensor_path(monkeypatch):
    from maxxair_fan import config as cfg

    sensor.reset_sensor_path_cache()
    monkeypatch.setattr(cfg, "SENSOR_PATH_OVERRIDE", None)
    monkeypatch.setattr(
        sensor.glob,
        "glob",
        lambda pattern: ["/sys/bus/w1/devices/28-abc123/w1_slave"],
    )
    path = sensor.get_sensor_path()
    assert path == Path("/sys/bus/w1/devices/28-abc123/w1_slave")
    sensor.reset_sensor_path_cache()


def test_no_sensors_found(monkeypatch):
    from maxxair_fan import config as cfg

    sensor.reset_sensor_path_cache()
    monkeypatch.setattr(cfg, "SENSOR_PATH_OVERRIDE", None)
    monkeypatch.setattr(sensor.glob, "glob", lambda pattern: [])
    assert sensor.get_sensor_path() is None
    sensor.reset_sensor_path_cache()
