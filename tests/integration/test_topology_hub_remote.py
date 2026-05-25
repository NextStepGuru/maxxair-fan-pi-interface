from maxxair_fan import main
from maxxair_fan.backends import (
    FakeSensorBackend,
    InMemoryFirebaseBackend,
)
from maxxair_fan.backends.remote_agent import RemoteAgentBackend
from maxxair_fan.fans_config import FanSpec


def test_topology_hub_three_remote(fake_agent_server):
    fb = InMemoryFirebaseBackend(
        {
            "fans": {
                "fan1": {"targetTemp": 72.0, "direction": "in"},
                "fan2": {"targetTemp": 72.0, "direction": "in"},
                "fan3": {"targetTemp": 72.0, "direction": "in"},
            }
        }
    )

    servers = []
    units = []
    temps = [75.0, 73.0, 72.0]
    for index, temp in enumerate(temps, start=1):
        server, ir, sensor = fake_agent_server(sensor=FakeSensorBackend(temp=temp))
        servers.append(server)
        sensor.set_temp(temp)
        spec = FanSpec(
            id=f"fan{index}",
            firebase_node=f"fans/fan{index}",
            agent_url=server.url,
        )
        remote = RemoteAgentBackend(server.url)
        from maxxair_fan.backends import wrap_ir_backend
        from maxxair_fan.fan_unit import FanUnit

        units.append(
            FanUnit(
                spec=spec,
                sensor_be=remote,
                ir_be=wrap_ir_backend(remote),
            )
        )

    main.run_multi_fan_iteration(units, fb, now=1000.0)

    assert fb.get("fans/fan1")["currentTemp"] == 75.0
    assert fb.get("fans/fan2")["currentTemp"] == 73.0
    assert fb.get("fans/fan3")["currentTemp"] == 72.0
    assert fb.get("fans/fan1")["online"] is True
    assert fb.get("fans/fan2")["online"] is True
    assert fb.get("fans/fan3")["online"] is True
