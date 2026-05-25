from pathlib import Path

from maxxair_fan import config
from maxxair_fan.backends.deduping_ir import DedupingIRBackend
from maxxair_fan.backends.fake_ir import FakeIRBackend
from maxxair_fan.backends.fake_sensor import FakeSensorBackend
from maxxair_fan.backends.firebase_rest import FirebaseRestBackend
from maxxair_fan.backends.in_memory_firebase import InMemoryFirebaseBackend
from maxxair_fan.backends.irctl import IrCtlBackend
from maxxair_fan.backends.protocols import FirebaseBackend, IRBackend, SensorBackend
from maxxair_fan.backends.remote_agent import RemoteAgentBackend
from maxxair_fan.backends.w1_sensor import W1SensorBackend
from maxxair_fan.fan_unit import FanUnit
from maxxair_fan.fans_config import FanSpec, load_fans_config


def _resolve_backend_name(specific: str | None, simulator_default: str, pi_default: str) -> str:
    if specific:
        return specific
    if config.MAXXAIR_BACKEND == "simulator":
        return simulator_default
    return pi_default


def wrap_ir_backend(ir_be: IRBackend) -> DedupingIRBackend:
    if isinstance(ir_be, DedupingIRBackend):
        return ir_be
    return DedupingIRBackend(ir_be)


def build_fan_unit(
    spec: FanSpec,
    *,
    fake_sensor: FakeSensorBackend | None = None,
    fake_ir: FakeIRBackend | None = None,
    dedupe_ir: bool = True,
) -> FanUnit:
    if spec.is_remote:
        if spec.agent_url is None:
            raise ValueError(f"Fan {spec.id!r} is remote but agent_url is missing")
        remote = RemoteAgentBackend(spec.agent_url, agent_token=spec.agent_token)
        ir_be: IRBackend = wrap_ir_backend(remote) if dedupe_ir else remote
        return FanUnit(spec=spec, sensor_be=remote, ir_be=ir_be)

    local = spec.local
    if local is None:
        raise ValueError(f"Fan {spec.id!r} has no local or remote configuration")

    sensor_be: SensorBackend = fake_sensor or W1SensorBackend(sensor_path=local.sensor_path)
    inner_ir: IRBackend = fake_ir or IrCtlBackend(ir_device=local.ir_device)
    ir_be = wrap_ir_backend(inner_ir) if dedupe_ir else inner_ir
    return FanUnit(spec=spec, sensor_be=sensor_be, ir_be=ir_be)


def build_backends(
    sensor_backend: str | None = None,
    ir_backend: str | None = None,
    firebase_backend: str | None = None,
    fake_sensor: FakeSensorBackend | None = None,
    fake_ir: FakeIRBackend | None = None,
    memory_firebase: InMemoryFirebaseBackend | None = None,
    dedupe_ir: bool = True,
) -> tuple[SensorBackend, IRBackend, FirebaseBackend]:
    sensor_name = _resolve_backend_name(sensor_backend, "fake", "w1")
    ir_name = _resolve_backend_name(ir_backend, "fake", "irctl")
    firebase_name = _resolve_backend_name(firebase_backend, "memory", "rest")

    if sensor_name == "fake":
        sensor_be: SensorBackend = fake_sensor or FakeSensorBackend.from_config(
            config.FAKE_SENSOR_TEMP
        )
    elif sensor_name == "w1":
        sensor_be = W1SensorBackend()
    else:
        raise ValueError(f"Unknown sensor backend: {sensor_name}")

    if ir_name == "fake":
        log_path = Path(config.FAKE_IR_LOG) if config.FAKE_IR_LOG else None
        inner_ir: IRBackend = fake_ir or FakeIRBackend(log_path=log_path)
    elif ir_name == "irctl":
        inner_ir = IrCtlBackend()
    else:
        raise ValueError(f"Unknown IR backend: {ir_name}")

    ir_be: IRBackend = wrap_ir_backend(inner_ir) if dedupe_ir else inner_ir

    if firebase_name == "memory":
        fb_be: FirebaseBackend = memory_firebase or InMemoryFirebaseBackend()
    elif firebase_name == "rest":
        fb_be = FirebaseRestBackend()
    else:
        raise ValueError(f"Unknown firebase backend: {firebase_name}")

    return sensor_be, ir_be, fb_be


def load_fan_units(
    specs: list[FanSpec] | None = None,
    *,
    fake_sensors: dict[str, FakeSensorBackend] | None = None,
    fake_ir: dict[str, FakeIRBackend] | None = None,
) -> list[FanUnit]:
    if specs is None:
        specs = load_fans_config()
    fake_sensors = fake_sensors or {}
    fake_ir = fake_ir or {}
    return [
        build_fan_unit(
            spec,
            fake_sensor=fake_sensors.get(spec.id),
            fake_ir=fake_ir.get(spec.id),
        )
        for spec in specs
    ]


__all__ = [
    "DedupingIRBackend",
    "FirebaseBackend",
    "FirebaseRestBackend",
    "FakeIRBackend",
    "FakeSensorBackend",
    "IRBackend",
    "InMemoryFirebaseBackend",
    "IrCtlBackend",
    "RemoteAgentBackend",
    "SensorBackend",
    "W1SensorBackend",
    "build_backends",
    "build_fan_unit",
    "load_fan_units",
    "wrap_ir_backend",
]
