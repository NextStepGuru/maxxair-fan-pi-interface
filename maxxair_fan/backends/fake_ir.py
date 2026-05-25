import json
import logging
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class FakeIRBackend:
    """Records IR sends in memory and optionally appends to a JSON log file."""

    def __init__(self, log_path: Path | None = None) -> None:
        self.sent: list[str] = []
        self._log_path = log_path

    def send(self, filename: str) -> bool:
        self.sent.append(filename)
        logger.info("Fake IR send: %s", filename)

        if self._log_path is not None:
            self._append_log(filename)

        return True

    def _append_log(self, filename: str) -> None:
        events: list[dict] = []
        if self._log_path.exists():
            try:
                events = json.loads(self._log_path.read_text())
            except (json.JSONDecodeError, OSError):
                events = []

        events.append(
            {
                "filename": filename,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_path.write_text(json.dumps(events, indent=2) + "\n")

    def reset(self) -> None:
        self.sent.clear()
