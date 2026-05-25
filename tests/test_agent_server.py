import json
import urllib.error
import urllib.request

from maxxair_fan.backends import FakeSensorBackend


def _get(url: str, token: str = "") -> tuple[int, dict]:
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        return exc.code, json.loads(body) if body else {}


def _post(url: str, payload: dict, token: str = "") -> tuple[int, dict]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        return exc.code, json.loads(body) if body else {}


def test_agent_health(fake_agent_server):
    server, _, _ = fake_agent_server()
    status, body = _get(f"{server.url}/health")
    assert status == 200
    assert body["ok"] is True


def test_agent_temp(fake_agent_server):
    server, _, sensor = fake_agent_server()
    sensor.set_temp(74.0)
    status, body = _get(f"{server.url}/temp")
    assert status == 200
    assert body["temp_f"] == 74.0


def test_agent_ir(fake_agent_server):
    server, ir, _ = fake_agent_server()
    status, body = _post(f"{server.url}/ir", {"filename": "fan_on_in_40.ir"})
    assert status == 200
    assert ir.sent == ["fan_on_in_40.ir"]


def test_agent_auth_required(fake_agent_server):
    server, _, _ = fake_agent_server(token="secret")
    status, _ = _get(f"{server.url}/temp")
    assert status == 401

    status, body = _get(f"{server.url}/temp", token="secret")
    assert status == 200
    assert "temp_f" in body


def test_agent_sensor_failure(fake_agent_server):
    class NullSensor(FakeSensorBackend):
        def read_temp_f(self):
            return None

    server, _, _ = fake_agent_server(sensor=NullSensor())
    status, body = _get(f"{server.url}/temp")
    assert status == 503
    assert "error" in body
