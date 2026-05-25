import logging
import time

import requests

from maxxair_fan import config

logger = logging.getLogger(__name__)

_consecutive_failures = 0


def reset_backoff_state() -> None:
    """Reset Firebase backoff counter (for tests)."""
    global _consecutive_failures
    _consecutive_failures = 0


def _apply_backoff() -> None:
    global _consecutive_failures
    if _consecutive_failures <= 0:
        return
    delay = min(2**_consecutive_failures, 60)
    logger.debug("Firebase backoff: sleeping %.1fs after %d failures", delay, _consecutive_failures)
    time.sleep(delay)


def _record_success() -> None:
    global _consecutive_failures
    _consecutive_failures = 0


def _record_failure() -> None:
    global _consecutive_failures
    _consecutive_failures += 1


def fb_get(path: str):
    if not config.FIREBASE_URL:
        logger.warning("FIREBASE_URL not configured; skipping GET")
        return None

    params = {}
    if config.FIREBASE_SECRET:
        params["auth"] = config.FIREBASE_SECRET

    url = f"{config.FIREBASE_URL.rstrip('/')}/{path}.json"
    _apply_backoff()
    try:
        response = requests.get(url, params=params, timeout=3)
        response.raise_for_status()
        _record_success()
        return response.json()
    except requests.RequestException as exc:
        _record_failure()
        logger.warning("Firebase GET failed for %s: %s", path, exc)
        return None


def fb_patch(path: str, data: dict) -> bool:
    if not config.FIREBASE_URL:
        logger.warning("FIREBASE_URL not configured; skipping PATCH")
        return False

    params = {}
    if config.FIREBASE_SECRET:
        params["auth"] = config.FIREBASE_SECRET

    url = f"{config.FIREBASE_URL.rstrip('/')}/{path}.json"
    _apply_backoff()
    try:
        response = requests.patch(url, params=params, json=data, timeout=3)
        response.raise_for_status()
        _record_success()
        return True
    except requests.RequestException as exc:
        _record_failure()
        logger.warning("Firebase PATCH failed for %s: %s", path, exc)
        return False
