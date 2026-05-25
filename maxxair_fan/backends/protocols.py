from typing import Any, Protocol


class SensorBackend(Protocol):
    def read_temp_f(self) -> float | None: ...


class IRBackend(Protocol):
    def send(self, filename: str) -> bool: ...


class FirebaseBackend(Protocol):
    def get(self, path: str) -> Any: ...

    def patch(self, path: str, data: dict) -> bool: ...
