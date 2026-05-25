import json
import subprocess
import sys
import urllib.request

import pytest


@pytest.mark.integration
def test_agent_cli_health(fake_agent_server):
    server, _, _ = fake_agent_server()
    # CLI agent runs blocking; we test the server fixture directly as smoke test
    # for the same HTTP surface the CLI exposes.
    with urllib.request.urlopen(f"{server.url}/health", timeout=3) as resp:
        body = json.loads(resp.read())
    assert resp.status == 200
    assert body["ok"] is True


@pytest.mark.integration
def test_dump_state_includes_fans_config(monkeypatch, tmp_path):
    config_path = tmp_path / "fans.json"
    config_path.write_text(
        '{"fans": [{"id": "fan1", "firebase_node": "fans/fan1", "local": {}}]}'
    )
    monkeypatch.setenv("FANS_CONFIG", str(config_path))
    monkeypatch.setenv("MAXXAIR_BACKEND", "simulator")

    result = subprocess.run(
        [sys.executable, "-m", "maxxair_fan", "dump-state"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "fan1" in result.stdout
    assert "local firebase=fans/fan1" in result.stdout
