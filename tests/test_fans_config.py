import json

import pytest

from maxxair_fan import config
from maxxair_fan.fans_config import legacy_fan_spec, load_fans_config


def test_legacy_fan_spec(monkeypatch):
    monkeypatch.setattr(config, "FAN_NODE", "fans/bedroom")
    monkeypatch.setattr(config, "SENSOR_PATH_OVERRIDE", "/sys/sensor")
    monkeypatch.setattr(config, "IR_DEVICE", "/dev/lirc1")

    spec = legacy_fan_spec()
    assert spec.id == "bedroom"
    assert spec.firebase_node == "fans/bedroom"
    assert spec.local is not None
    assert spec.local.sensor_path == "/sys/sensor"
    assert spec.local.ir_device == "/dev/lirc1"


def test_load_fans_config_from_file(tmp_path):
    config_path = tmp_path / "fans.json"
    config_path.write_text(
        json.dumps(
            {
                "fans": [
                    {
                        "id": "a",
                        "firebase_node": "fans/a",
                        "local": {"sensor_path": "/s1"},
                    },
                    {
                        "id": "b",
                        "firebase_node": "fans/b",
                        "agent_url": "http://pi:8765",
                    },
                ]
            }
        )
    )
    specs = load_fans_config(config_path)
    assert len(specs) == 2
    assert specs[0].is_local
    assert specs[1].is_remote


def test_load_fans_config_rejects_both_local_and_remote(tmp_path):
    config_path = tmp_path / "bad.json"
    config_path.write_text(
        json.dumps(
            {
                "fans": [
                    {
                        "id": "x",
                        "firebase_node": "fans/x",
                        "local": {},
                        "agent_url": "http://pi:8765",
                    }
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="either 'local' or 'agent_url'"):
        load_fans_config(config_path)


def test_load_fans_config_rejects_duplicate_ids(tmp_path):
    config_path = tmp_path / "dup.json"
    config_path.write_text(
        json.dumps(
            {
                "fans": [
                    {"id": "fan1", "firebase_node": "fans/a", "local": {}},
                    {"id": "fan1", "firebase_node": "fans/b", "local": {}},
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="Duplicate fan id"):
        load_fans_config(config_path)


def test_load_fans_config_empty_fans(tmp_path):
    config_path = tmp_path / "empty.json"
    config_path.write_text(json.dumps({"fans": []}))
    with pytest.raises(ValueError, match="at least one fan"):
        load_fans_config(config_path)


def test_load_fans_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_fans_config("/nonexistent/fans.json")
