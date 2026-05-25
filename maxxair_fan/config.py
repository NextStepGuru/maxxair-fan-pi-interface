import logging
import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

REPO_ROOT = Path(__file__).resolve().parent.parent

CHECK_INTERVAL = float(os.environ.get("CHECK_INTERVAL", "2"))
GRADIENT_DEGREES = float(os.environ.get("GRADIENT_DEGREES", "0.5"))
EXPONENT_VALUE = float(os.environ.get("EXPONENT_VALUE", "2.0"))

IR_DIR = Path(os.environ.get("IR_DIR", str(REPO_ROOT / "ir_codes")))

FAN_NODE = os.environ.get("FAN_NODE", "fans/fan1")

SENSOR_PATH_OVERRIDE = os.environ.get("SENSOR_PATH")

FIREBASE_URL = os.environ.get("FIREBASE_URL", "")
FIREBASE_SECRET = os.environ.get("FIREBASE_SECRET", "")

TEMP_PATCH_THRESHOLD = float(os.environ.get("TEMP_PATCH_THRESHOLD", "0.1"))
PATCH_HEARTBEAT_SECONDS = float(os.environ.get("PATCH_HEARTBEAT_SECONDS", "60"))

FAN_OFF_ON_EXIT = os.environ.get("FAN_OFF_ON_EXIT", "false").lower() in (
    "1",
    "true",
    "yes",
)

LOCK_FILE = Path(os.environ.get("LOCK_FILE", "/tmp/maxxair-fan.lock"))

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

MAXXAIR_BACKEND = os.environ.get("MAXXAIR_BACKEND", "pi")
SENSOR_BACKEND = os.environ.get("SENSOR_BACKEND")
IR_BACKEND = os.environ.get("IR_BACKEND")
FIREBASE_BACKEND = os.environ.get("FIREBASE_BACKEND")
FAKE_SENSOR_TEMP = os.environ.get("FAKE_SENSOR_TEMP", "72.0")
FAKE_IR_LOG = os.environ.get("FAKE_IR_LOG", "")

MAXXAIR_SKIP_PREFLIGHT = os.environ.get("MAXXAIR_SKIP_PREFLIGHT", "false").lower() in (
    "1",
    "true",
    "yes",
)


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
