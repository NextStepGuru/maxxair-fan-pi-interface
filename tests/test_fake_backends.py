import json

from maxxair_fan.backends.fake_ir import FakeIRBackend
from maxxair_fan.backends.fake_sensor import FakeSensorBackend


def test_fake_sensor_from_config_json_series(tmp_path):
    path = tmp_path / "series.json"
    path.write_text('{"steps": [{"temp": 72.0}, {"temp": null}, {"temp": 75.5}]}\n')

    sensor = FakeSensorBackend.from_config(str(path))
    assert sensor.read_temp_f() == 72.0
    assert sensor.read_temp_f() is None
    assert sensor.read_temp_f() == 75.5


def test_fake_ir_appends_to_log_file(tmp_path):
    log_path = tmp_path / "ir-log.json"
    backend = FakeIRBackend(log_path=log_path)

    assert backend.send("fan_off.ir") is True
    assert backend.send("fan_on_in_50.ir") is True

    events = json.loads(log_path.read_text())
    assert len(events) == 2
    assert events[0]["filename"] == "fan_off.ir"
    assert events[1]["filename"] == "fan_on_in_50.ir"
    assert "timestamp" in events[0]
