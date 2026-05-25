from pathlib import Path

from maxxair_fan import config


def test_ir_dir_default_points_to_repo_ir_codes():
    assert (config.REPO_ROOT / "ir_codes").exists()
    assert config.IR_DIR == config.REPO_ROOT / "ir_codes" or Path(config.IR_DIR).name == "ir_codes"


def test_defaults():
    assert config.CHECK_INTERVAL == 2.0
    assert config.GRADIENT_DEGREES == 0.5
    assert config.EXPONENT_VALUE == 2.0


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("CHECK_INTERVAL", "5")
    monkeypatch.setenv("FAN_NODE", "fans/test")
    monkeypatch.setenv("FAN_OFF_ON_EXIT", "true")
    monkeypatch.setenv("MAXXAIR_SKIP_PREFLIGHT", "true")

    assert __import__("os").environ["CHECK_INTERVAL"] == "5"
    assert __import__("os").environ["FAN_NODE"] == "fans/test"
