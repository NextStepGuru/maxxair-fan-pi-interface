# Architecture

How the MaxxAir Fan Pi Interface reads temperature, syncs with Firebase, and controls the fan.

## Overview

```
┌─────────────┐     read/write      ┌──────────────────┐
│  Firebase   │◄───────────────────►│  maxxair_fan     │
│  RTDB       │  targetTemp,        │  daemon          │
│             │  direction, status  │                  │
└─────────────┘                     └────────┬─────────┘
                                             │
                              ┌──────────────┼──────────────┐
                              ▼              ▼              ▼
                        DS18B20         ir-ctl         (optional
                        1-wire          + .ir files     fake backends)
```

The daemon runs a loop every `CHECK_INTERVAL` seconds (default 2). Each tick iterates all configured fans (from `FANS_CONFIG` or legacy single-fan env):

1. **Read** `targetTemp` and `direction` from Firebase (per fan node)
2. **Read** current temperature from sensor (local or remote agent)
3. **Compute** fan speed (0–100% in 10% steps) using the exponential curve
4. **Send** the matching pre-recorded IR code (skipped if unchanged)
5. **Write** status telemetry back to Firebase

Multi-fan deployments: [Topologies](topologies.md).

## Control loop

Each iteration in `maxxair_fan/main.py`:

| Step | Action |
| --- | --- |
| Fetch config | GET `targetTemp`, `direction` from `FAN_NODE` |
| Read sensor | DS18B20 via `/sys/bus/w1/devices/28-*/w1_slave` |
| Compute speed | `fan.compute_speed(current, target)` |
| Resolve IR file | e.g. `fan_on_in_40.ir` or `fan_off.ir` |
| Send IR | `ir-ctl -s` via backend (deduped if same as last send) |
| Patch Firebase | Status fields when temp changes ≥ threshold or on heartbeat |

Firebase writes are throttled:

- Temperature updates when change ≥ `TEMP_PATCH_THRESHOLD` (default 0.1°F)
- Status heartbeat at least every `PATCH_HEARTBEAT_SECONDS` (default 60s)

## Fan speed curve

Algorithm by **Ryder Henry**. When room temperature is **above** target:

```
speed = 10 × exponent^((diff / gradient) - 1)
```

Rounded to nearest 10%, capped at 100%. At or below target → fan off (0%).

Default `GRADIENT_DEGREES=0.5`, `EXPONENT_VALUE=2.0`:

| Above target | Speed |
| --- | --- |
| 0.5°F | 10% |
| 1.0°F | 20% |
| 1.5°F | 40% |
| 2.0°F | 80% |
| ≥ 2.5°F | 100% |

Preview the curve for your settings:

```bash
maxxair-fan simulate --temp 74.0 --target 72.0
```

See [Configuration → Fan speed curve](configuration.md#fan-speed-curve) for tuning variables.

## IR codes

Pre-recorded signals live in [`ir_codes/`](../ir_codes/):

| Pattern | Example |
| --- | --- |
| Off | `fan_off.ir` |
| Intake at N% | `fan_on_in_10.ir` … `fan_on_in_100.ir` |
| Exhaust at N% | `fan_on_out_10.ir` … `fan_on_out_100.ir` |

Filename resolution is in `maxxair_fan/fan.py` → `resolve_ir_filename()`.

## Backends

Hardware access is abstracted so the same loop runs on a Pi or in simulation.

| Backend | `MAXXAIR_BACKEND` | Sensor | IR | Firebase |
| --- | --- | --- | --- | --- |
| Pi (default) | `pi` | `w1` (DS18B20) | `irctl` | `rest` |
| Simulator | `simulator` | `fake` | `fake` | `memory` or `rest` |

Override individual layers with `SENSOR_BACKEND`, `IR_BACKEND`, and `FIREBASE_BACKEND`. See [Configuration → Backends](configuration.md#backends).

`DedupingIRBackend` wraps the IR backend and skips sending when the resolved filename matches the previous send.

## Process lifecycle

- **Single instance:** flock lock at `LOCK_FILE` (default `/tmp/maxxair-fan.lock`)
- **Signals:** SIGINT/SIGTERM set a shutdown flag; loop exits cleanly
- **Optional shutdown IR:** `FAN_OFF_ON_EXIT=true` sends `fan_off.ir` on exit
- **Preflight:** On Pi startup, validates Firebase, sensor, IR dir, and `ir-ctl` unless `MAXXAIR_SKIP_PREFLIGHT=true`

## Package layout

```
maxxair_fan/
  main.py          Control loop, preflight, Firebase patch logic
  fan.py           Speed curve and IR filename resolution
  sensor.py        DS18B20 reading with CRC retry
  firebase.py      REST GET/PATCH helpers
  config.py        Environment-based settings
  cli.py           Subcommands (run, check, simulate, …)
  backends/        Pi vs fake implementations
  devtools/        Fake Firebase HTTP server and live TUI
ir_codes/          Recorded MaxxAir IR signals
tests/             Unit and integration tests
```

## Related docs

- [Firebase schema](firebase-schema.md) — fields written to RTDB
- [CLI reference](cli.md) — run, check, simulate, replay
- [Development](development.md) — fake backends and replay fixtures
