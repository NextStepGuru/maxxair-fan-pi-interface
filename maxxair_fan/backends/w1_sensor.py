from pathlib import Path

from maxxair_fan import sensor


class W1SensorBackend:
    def __init__(self, sensor_path: str | Path | None = None) -> None:
        self.sensor_path = Path(sensor_path) if sensor_path else None

    def read_temp_f(self) -> float | None:
        return sensor.read_temp_f(self.sensor_path)
