import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class FakeSensorBackend:
    """Returns configured temperatures, optionally from a JSON step series."""

    def __init__(
        self,
        temp: float | None = 72.0,
        series: list[float | None] | None = None,
    ) -> None:
        self._static_temp = temp
        self._series = list(series) if series else []
        self._index = 0

    @classmethod
    def from_config(cls, value: str) -> "FakeSensorBackend":
        path = Path(value)
        if path.is_file():
            data = json.loads(path.read_text())
            if isinstance(data, dict) and "steps" in data:
                temps = [
                    None if step.get("temp") is None else float(step["temp"])
                    for step in data["steps"]
                ]
                return cls(series=temps)
            if isinstance(data, list):
                return cls(series=[float(x) for x in data])
            raise ValueError(f"Unsupported fake sensor JSON format: {path}")

        return cls(temp=float(value))

    def read_temp_f(self) -> float | None:
        if self._series:
            if self._index >= len(self._series):
                temp = self._series[-1]
            else:
                temp = self._series[self._index]
                self._index += 1
            logger.debug("Fake sensor read: %.2f°F (step %d)", temp, self._index)
            return temp

        logger.debug("Fake sensor read: %.2f°F (static)", self._static_temp)
        return self._static_temp

    def set_temp(self, temp: float) -> None:
        self._static_temp = temp
        self._series = []
        self._index = 0

    def set_series(self, series: list[float | None]) -> None:
        self._series = list(series)
        self._index = 0

    def reset(self) -> None:
        self._index = 0
