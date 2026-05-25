import json
from pathlib import Path

import pytest

from maxxair_fan.agent import AgentContext, AgentServer
from maxxair_fan.backends import FakeIRBackend, FakeSensorBackend

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "topologies"


def load_topology(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


@pytest.fixture
def mock_subprocess_run(mocker):
    return mocker.patch("maxxair_fan.fan.subprocess.run", return_value=mocker.Mock(returncode=0))


@pytest.fixture
def fake_agent_server():
    """Thread-local HTTP agent with injectable fake sensor and IR."""
    servers: list[AgentServer] = []

    def _start(
        *,
        sensor: FakeSensorBackend | None = None,
        ir: FakeIRBackend | None = None,
        token: str = "",
    ) -> tuple[AgentServer, FakeIRBackend, FakeSensorBackend]:
        fake_ir = ir or FakeIRBackend()
        fake_sensor = sensor or FakeSensorBackend(temp=72.0)
        context = AgentContext(
            sensor_be=fake_sensor,
            ir_be=fake_ir,
            agent_token=token,
        )
        server = AgentServer(bind="127.0.0.1", port=0, context=context)
        server.start(background=True)
        servers.append(server)
        return server, fake_ir, fake_sensor

    yield _start

    for server in servers:
        server.stop()
