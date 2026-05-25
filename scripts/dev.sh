#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

mkdir -p .dev

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements-dev.txt
fi

PYTHON=".venv/bin/python"

$PYTHON -m maxxair_fan.devtools.fake_firebase --port 9000 --state .dev/firebase.json &
FAKE_PID=$!
trap 'kill "$FAKE_PID" 2>/dev/null || true' EXIT
sleep 0.3

FIREBASE_URL=http://localhost:9000 \
MAXXAIR_BACKEND=simulator \
SENSOR_BACKEND=fake \
IR_BACKEND=fake \
FIREBASE_BACKEND=rest \
FAKE_SENSOR_TEMP=73.5 \
$PYTHON -m maxxair_fan run --tui
