"""HTTP client backend for remote Pi edge agents."""

from __future__ import annotations

import logging

import requests

from maxxair_fan import config

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 3


class RemoteAgentBackend:
    """Read temperature and send IR via a remote edge agent."""

    def __init__(
        self,
        agent_url: str,
        agent_token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = agent_url.rstrip("/")
        self.agent_token = agent_token or config.AGENT_TOKEN or None
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        if self.agent_token:
            return {"Authorization": f"Bearer {self.agent_token}"}
        return {}

    def health_check(self) -> bool:
        try:
            response = requests.get(
                f"{self.base_url}/health",
                headers=self._headers(),
                timeout=self.timeout,
            )
            return response.status_code == 200
        except requests.RequestException as exc:
            logger.warning("Agent health check failed for %s: %s", self.base_url, exc)
            return False

    def read_temp_f(self) -> float | None:
        try:
            response = requests.get(
                f"{self.base_url}/temp",
                headers=self._headers(),
                timeout=self.timeout,
            )
            if response.status_code != 200:
                logger.warning(
                    "Agent temp read failed for %s: HTTP %s",
                    self.base_url,
                    response.status_code,
                )
                return None
            data = response.json()
            temp = data.get("temp_f")
            if temp is None:
                return None
            return float(temp)
        except (requests.RequestException, TypeError, ValueError) as exc:
            logger.warning("Agent temp read failed for %s: %s", self.base_url, exc)
            return None

    def send(self, filename: str) -> bool:
        try:
            response = requests.post(
                f"{self.base_url}/ir",
                headers={**self._headers(), "Content-Type": "application/json"},
                json={"filename": filename},
                timeout=self.timeout,
            )
            if response.status_code == 200:
                return True
            logger.warning(
                "Agent IR send failed for %s: HTTP %s",
                self.base_url,
                response.status_code,
            )
            return False
        except requests.RequestException as exc:
            logger.warning("Agent IR send failed for %s: %s", self.base_url, exc)
            return False
