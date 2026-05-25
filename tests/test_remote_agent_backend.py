import responses

from maxxair_fan.backends.remote_agent import RemoteAgentBackend


@responses.activate
def test_remote_agent_health_check():
    responses.add(responses.GET, "http://agent/health", json={"ok": True}, status=200)
    backend = RemoteAgentBackend("http://agent")
    assert backend.health_check() is True


@responses.activate
def test_remote_agent_read_temp():
    responses.add(responses.GET, "http://agent/temp", json={"temp_f": 73.5}, status=200)
    backend = RemoteAgentBackend("http://agent")
    assert backend.read_temp_f() == 73.5


@responses.activate
def test_remote_agent_send_ir():
    responses.add(responses.POST, "http://agent/ir", json={"ok": True}, status=200)
    backend = RemoteAgentBackend("http://agent")
    assert backend.send("fan_on_in_50.ir") is True


@responses.activate
def test_remote_agent_auth_header():
    responses.add(responses.GET, "http://agent/temp", json={"temp_f": 72.0}, status=200)
    backend = RemoteAgentBackend("http://agent", agent_token="secret")
    backend.read_temp_f()
    assert responses.calls[0].request.headers["Authorization"] == "Bearer secret"


@responses.activate
def test_remote_agent_temp_failure():
    responses.add(responses.GET, "http://agent/temp", status=503)
    backend = RemoteAgentBackend("http://agent")
    assert backend.read_temp_f() is None


@responses.activate
def test_remote_agent_ir_failure():
    responses.add(responses.POST, "http://agent/ir", status=500)
    backend = RemoteAgentBackend("http://agent")
    assert backend.send("fan_off.ir") is False
