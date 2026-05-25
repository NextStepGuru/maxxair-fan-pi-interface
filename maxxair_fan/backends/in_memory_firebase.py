import copy
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _path_parts(path: str) -> list[str]:
    return [part for part in path.strip("/").split("/") if part]


def _get_node(root: dict, path: str) -> Any:
    node: Any = root
    for part in _path_parts(path):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return copy.deepcopy(node)


def _set_node(root: dict, path: str, value: dict) -> None:
    parts = _path_parts(path)
    if not parts:
        root.clear()
        root.update(value)
        return

    node = root
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = copy.deepcopy(value)


def _merge_node(root: dict, path: str, patch: dict) -> None:
    existing = _get_node(root, path)
    if existing is None:
        _set_node(root, path, patch)
        return

    if not isinstance(existing, dict):
        _set_node(root, path, patch)
        return

    merged = copy.deepcopy(existing)
    merged.update(patch)
    _set_node(root, path, merged)


class InMemoryFirebaseBackend:
    """Dict-backed Firebase RTDB emulator for local testing."""

    def __init__(self, initial_state: dict | None = None) -> None:
        self.state: dict = copy.deepcopy(initial_state or {})

    def get(self, path: str):
        value = _get_node(self.state, path)
        logger.debug("In-memory Firebase GET %s -> %r", path, value)
        return value

    def patch(self, path: str, data: dict) -> bool:
        _merge_node(self.state, path, data)
        logger.debug("In-memory Firebase PATCH %s <- %r", path, data)
        return True

    def put(self, path: str, data: dict) -> None:
        _set_node(self.state, path, data)
