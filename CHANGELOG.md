# Changelog

All notable changes to this project are documented in this file.

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
