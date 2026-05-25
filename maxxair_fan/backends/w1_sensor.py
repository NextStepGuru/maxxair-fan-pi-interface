from maxxair_fan import sensor


class W1SensorBackend:
    def read_temp_f(self) -> float | None:
        return sensor.read_temp_f()
