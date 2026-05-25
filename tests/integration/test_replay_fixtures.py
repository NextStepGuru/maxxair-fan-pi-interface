from pathlib import Path

import pytest

from maxxair_fan.devtools.replay import run_replay_fixture_path

pytestmark = pytest.mark.integration

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.mark.parametrize(
    "fixture_name",
    [
        "heating_up.json",
        "direction_change.json",
        "cooling_below.json",
        "noisy_sensor.json",
        "target_change.json",
        "sensor_outage.json",
        "at_target_stable.json",
    ],
)
def test_replay_fixtures_match_expected(fixture_name):
    fixture_path = FIXTURES_DIR / fixture_name
    sent, _fb = run_replay_fixture_path(fixture_path)
    import json

    fixture = json.loads(fixture_path.read_text())
    assert sent == fixture["expected_ir"]
