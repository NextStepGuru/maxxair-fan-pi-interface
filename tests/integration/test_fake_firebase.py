import json

import pytest

from maxxair_fan import config, firebase, main
from maxxair_fan.backends import (
    FakeIRBackend,
    FakeSensorBackend,
    FirebaseRestBackend,
    wrap_ir_backend,
)
from maxxair_fan.devtools.fake_firebase import run_server

pytestmark = pytest.mark.integration


@pytest.fixture
def fake_firebase_server(tmp_path):
    state_path = tmp_path / "firebase.json"
    httpd = run_server("127.0.0.1", 0, state_path)
    host, port = httpd.server_address
    base_url = f"http://{host}:{port}"

    yield base_url, state_path

    httpd.shutdown()


def test_fake_firebase_get_patch_persist(fake_firebase_server, monkeypatch):
    base_url, state_path = fake_firebase_server
    monkeypatch.setattr(config, "FIREBASE_URL", base_url)
    monkeypatch.setattr(config, "FIREBASE_SECRET", "")
    firebase.reset_backoff_state()

    assert firebase.fb_get("fans/fan1") == {"targetTemp": 72.0, "direction": "in"}

    assert firebase.fb_patch("fans/fan1", {"currentTemp": 75.0, "lastUpdate": "t1"}) is True
    updated = firebase.fb_get("fans/fan1")
    assert updated["currentTemp"] == 75.0
    assert updated["targetTemp"] == 72.0

    saved = json.loads(state_path.read_text())
    assert saved["fans"]["fan1"]["currentTemp"] == 75.0


def test_loop_iteration_patches_via_rest_firebase(fake_firebase_server, monkeypatch):
    base_url, _state_path = fake_firebase_server
    monkeypatch.setattr(config, "FIREBASE_URL", base_url)
    monkeypatch.setattr(config, "FIREBASE_SECRET", "")
    monkeypatch.setattr(config, "FAN_NODE", "fans/fan1")
    firebase.reset_backoff_state()

    sensor = FakeSensorBackend(temp=75.0)
    ir = wrap_ir_backend(FakeIRBackend())
    fb = FirebaseRestBackend()

    main.run_loop_iteration(72.0, "in", None, None, sensor, ir, fb, now=1000.0)

    node = firebase.fb_get("fans/fan1")
    assert node["currentTemp"] == 75.0
    assert node["sensorOk"] is True
    assert ir.inner.sent == ["fan_on_in_100.ir"]
