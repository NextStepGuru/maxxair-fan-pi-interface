"""Fan registry: JSON config loader and legacy single-fan env shim."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from maxxair_fan import config


@dataclass(frozen=True)
class LocalFanConfig:
    sensor_path: str | None = None
    ir_device: str | None = None


@dataclass(frozen=True)
class FanSpec:
    id: str
    firebase_node: str
    local: LocalFanConfig | None = None
    agent_url: str | None = None
    agent_token: str | None = None

    @property
    def is_local(self) -> bool:
        return self.local is not None

    @property
    def is_remote(self) -> bool:
        return self.agent_url is not None


def legacy_fan_spec() -> FanSpec:
    """Build a single-fan spec from legacy environment variables."""
    local = LocalFanConfig(
        sensor_path=config.SENSOR_PATH_OVERRIDE,
        ir_device=config.IR_DEVICE,
    )
    fan_id = config.FAN_NODE.rsplit("/", maxsplit=1)[-1]
    return FanSpec(
        id=fan_id,
        firebase_node=config.FAN_NODE,
        local=local,
    )


def _parse_fan_entry(entry: dict) -> FanSpec:
    fan_id = entry.get("id")
    firebase_node = entry.get("firebase_node")
    if not fan_id or not firebase_node:
        raise ValueError("Each fan requires 'id' and 'firebase_node'")

    has_local = "local" in entry and entry["local"] is not None
    has_agent = bool(entry.get("agent_url"))

    if has_local and has_agent:
        raise ValueError(f"Fan {fan_id!r}: specify either 'local' or 'agent_url', not both")
    if not has_local and not has_agent:
        raise ValueError(f"Fan {fan_id!r}: requires 'local' or 'agent_url'")

    local: LocalFanConfig | None = None
    if has_local:
        local_data = entry["local"] or {}
        local = LocalFanConfig(
            sensor_path=local_data.get("sensor_path"),
            ir_device=local_data.get("ir_device"),
        )

    return FanSpec(
        id=str(fan_id),
        firebase_node=str(firebase_node),
        local=local,
        agent_url=entry.get("agent_url"),
        agent_token=entry.get("agent_token"),
    )


def _validate_specs(specs: list[FanSpec]) -> None:
    if not specs:
        raise ValueError("Fan registry must contain at least one fan")

    seen_ids: set[str] = set()
    seen_nodes: set[str] = set()
    for spec in specs:
        if spec.id in seen_ids:
            raise ValueError(f"Duplicate fan id: {spec.id!r}")
        if spec.firebase_node in seen_nodes:
            raise ValueError(f"Duplicate firebase_node: {spec.firebase_node!r}")
        seen_ids.add(spec.id)
        seen_nodes.add(spec.firebase_node)


def load_fans_config(path: Path | str | None = None) -> list[FanSpec]:
    """Load fan registry from JSON file, or legacy env when path is unset."""
    if path is None:
        path = config.FANS_CONFIG

    if not path:
        specs = [legacy_fan_spec()]
        _validate_specs(specs)
        return specs

    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"FANS_CONFIG not found: {config_path}")

    data = json.loads(config_path.read_text())
    fans = data.get("fans")
    if not isinstance(fans, list):
        raise ValueError("FANS_CONFIG JSON must contain a 'fans' array")

    specs = [_parse_fan_entry(entry) for entry in fans]
    _validate_specs(specs)
    return specs
