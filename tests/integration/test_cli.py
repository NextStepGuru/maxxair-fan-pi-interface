import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]


def run_cli(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    import os

    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, "-m", "maxxair_fan", *args],
        cwd=REPO_ROOT,
        env=merged,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_simulate():
    result = run_cli("simulate", "--temp", "73.5", "--target", "72")
    assert result.returncode == 0
    assert "speed=40%" in result.stdout
    assert "fan_on_in_40.ir" in result.stdout


def test_cli_send_ir_fake_backend():
    result = run_cli(
        "send-ir",
        "fan_off.ir",
        env={
            "MAXXAIR_BACKEND": "simulator",
            "SENSOR_BACKEND": "fake",
            "IR_BACKEND": "fake",
            "FIREBASE_BACKEND": "memory",
        },
    )
    assert result.returncode == 0


def test_cli_run_once_simulator():
    result = run_cli("run", "--simulator", "--once")
    assert result.returncode == 0


def test_cli_dump_state():
    result = run_cli("dump-state")
    assert result.returncode == 0
    assert "MAXXAIR_BACKEND=" in result.stdout
    assert "IR_DIR=" in result.stdout


def test_cli_replay_heating_up():
    fixture = REPO_ROOT / "tests" / "fixtures" / "heating_up.json"
    result = run_cli("replay", str(fixture))
    assert result.returncode == 0
    assert "fan_on_in_10.ir" in result.stdout
    assert "IR commands sent:" in result.stdout


def test_cli_check_simulator():
    result = run_cli("check", env={"MAXXAIR_BACKEND": "simulator"})
    assert result.returncode == 0
    assert "OK: runtime preflight passed" in result.stdout


@pytest.mark.parametrize(
    "fixture_name",
    [
        "target_change.json",
        "sensor_outage.json",
        "at_target_stable.json",
    ],
)
def test_cli_replay_new_fixtures(fixture_name):
    fixture = REPO_ROOT / "tests" / "fixtures" / fixture_name
    result = run_cli("replay", str(fixture))
    assert result.returncode == 0
    assert "IR commands sent:" in result.stdout
