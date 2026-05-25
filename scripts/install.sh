#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

.venv/bin/pip install -r requirements.txt

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example — edit Firebase credentials before running."
fi

if [[ "${1:-}" == "--systemd" ]]; then
  sudo cp deploy/maxxair-fan.service /etc/systemd/system/
  sudo sed -i "s|/home/pi/maxxair-fan-pi-interface|${REPO_DIR}|g" /etc/systemd/system/maxxair-fan.service
  sudo systemctl daemon-reload
  sudo systemctl enable maxxair-fan.service
  echo "Installed systemd unit. Start with: sudo systemctl start maxxair-fan"
  echo "Logs: journalctl -u maxxair-fan -f"
fi

echo "Install complete. Run manually with: .venv/bin/python -m maxxair_fan run"
echo "Preflight: .venv/bin/python -m maxxair_fan check"
