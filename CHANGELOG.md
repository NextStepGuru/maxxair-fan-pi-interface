# Changelog

All notable changes to this project are documented in this file.

## Unreleased

### Added
- AtomS3 Lite firmware (`firmware/atoms3-agent/`) implementing the remote-agent HTTP API for three MaxxAir fans
- `scripts/ir_to_rmt.py` to compile `ir_codes/*.ir` into ESP32 PROGMEM raw timings
- Hub example [`config/examples/hub-atoms3.json`](config/examples/hub-atoms3.json) and [AtomS3 Lite agent guide](docs/atoms3-agent.md)
- Docs for hub + three AtomS3 Lite agents (README, topologies 2b, architecture, CLI, Firebase schema)

### Changed
- Remote agent HTTP timeout increased from 3s to 5s to cover DS18B20 conversion plus IR send

## [1.1.0] - 2026-05-25

### Added
- Backend abstraction layer with Pi and simulator implementations
- CLI (`python -m maxxair_fan`) with `run`, `check`, `send-ir`, `simulate`, `replay`, `dump-state`
- Local fake Firebase HTTP server and `./scripts/dev.sh` quickstart
- Integration tests and replay fixtures
- Startup preflight validation and `check` subcommand
- Firebase status telemetry (`online`, `sensorOk`, `irOk`, `lastIrCommand`, `lastError`)
- DS18B20 CRC retry and `sensorCrcFailures` counter
- `DedupingIRBackend` wrapper (replaces module-global IR dedupe state)
- systemd hardening, pip-installable package, ruff linting, CI matrix 3.11/3.12

### Fixed
- Firebase PATCH now sends `Content-Type: application/json`
- IR file existence checked before calling `ir-ctl`
- Sensor read failures now publish heartbeat status to Firebase

### Changed
- Default `CHECK_INTERVAL` increased to 2 seconds for DS18B20 timing
- Package version bumped to 1.1.0

## [1.0.0] - 2026-05-25

### Added
- Modular `maxxair_fan/` package refactored from original `ir.py`
- Environment-based configuration, logging, Firebase write throttling
- SIGTERM/SIGINT handling and single-instance flock lock
- DS18B20 auto-detection, pytest suite, systemd unit, GitHub Actions CI

### Credit
- Original algorithm and design by **Ryder Henry**
