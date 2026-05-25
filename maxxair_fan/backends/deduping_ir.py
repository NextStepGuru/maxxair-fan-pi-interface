from maxxair_fan.backends.protocols import IRBackend


class DedupingIRBackend:
    """Wraps an IR backend and suppresses duplicate consecutive sends."""

    def __init__(self, inner: IRBackend) -> None:
        self.inner = inner
        self.last_sent: str | None = None

    def send(self, filename: str) -> bool:
        if filename == self.last_sent:
            return True
        if self.inner.send(filename):
            self.last_sent = filename
            return True
        return False

    def reset(self) -> None:
        self.last_sent = None
