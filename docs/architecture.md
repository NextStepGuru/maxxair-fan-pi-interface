# Architecture

How the MaxxAir Fan Pi Interface reads temperature, syncs with Firebase, and controls the fan.

## Overview

```
┌─────────────┐     read/write      ┌──────────────────┐
│  Firebase   │◄───────────────────►│  maxxair_fan     │
│  RTDB       │  targetTemp,        │  hub daemon      │
│             │  direction, status  │                  │
└─────────────┘                     └────────┬─────────┘
                                             │
                    ┌────────────────────────┼────────────────────────┐
                    ▼                        ▼                        ▼
              local DS18B20            remote HTTP agent         (optional
              + ir-ctl                 (Pi or AtomS3 Lite)        fake backends)
                                       DS18B20 + IR
```

The daemon runs a loop every `CHECK_INTERVAL` seconds (default 2). Each tick iterates all configured fans (from `FANS_CONFIG` or legacy single-fan env):

1. **Read** `targetTemp` and `direction` from Firebase (per fan node)
2. **Read** current temperature from sensor (local or remote agent)
3. **Compute** fan speed (0–100% in 10% steps) using the exponential curve
4. **Send** the matching pre-recorded IR code (skipped if unchanged)
5. **Write** status telemetry back to Firebase

Multi-fan deployments, including three AtomS3 Lite agents: [Topologies](topologies.md).

## Control loop

Each iteration in `maxxair_fan/main.py`:

| Step | Action |
| --- | --- |
| Fetch config | GET `targetTemp`, `direction` from the fan's Firebase node |
| Read sensor | Local DS18B20 via `/sys/bus/w1/devices/28-*/w1_slave`, or `GET /temp` on a remote agent |
| Compute speed | `fan.compute_speed(current, target)` |
| Resolve IR file | e.g. `fan_on_in_40.ir` or `fan_off.ir` |
| Send IR | Local `ir-ctl -s`, or `POST /ir` on a remote agent (deduped if same as last send) |
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

Filename resolution is in `maxxair_fan/fan.py` → `resolve_ir_filename()`. AtomS3 Lite agents compile the same files to PROGMEM raw timings via [`scripts/ir_to_rmt.py`](../scripts/ir_to_rmt.py).

## Backends

Hardware access is abstracted so the same loop runs on a Pi, against remote agents, or in simulation.

| Backend | How selected | Sensor | IR | Firebase |
| --- | --- | --- | --- | --- |
| Pi (default) | `MAXXAIR_BACKEND=pi` | `w1` (DS18B20) | `irctl` | `rest` |
| Remote agent | `FANS_CONFIG` `agent_url` | HTTP `GET /temp` | HTTP `POST /ir` | `rest` on the hub |
| Simulator | `MAXXAIR_BACKEND=simulator` | `fake` | `fake` | `memory` or `rest` |

Remote agents may be a Pi running `maxxair-fan agent` or an [AtomS3 Lite](atoms3-agent.md). The hub still owns Firebase and IR filename dedupe.

Override individual local layers with `SENSOR_BACKEND`, `IR_BACKEND`, and `FIREBASE_BACKEND`. See [Configuration → Backends](configuration.md#backends).

`DedupingIRBackend` wraps the IR backend and skips sending when the resolved filename matches the previous send.

## Process lifecycle

- **Single instance:** flock lock at `LOCK_FILE` (default `/tmp/maxxair-fan.lock`)
- **Signals:** SIGINT/SIGTERM set a shutdown flag; loop exits cleanly
- **Optional shutdown IR:** `FAN_OFF_ON_EXIT=true` sends `fan_off.ir` on exit
- **Preflight:** Validates Firebase, then local `ir-ctl`/DS18B20 for local fans or agent `/health` for remote fans, unless `MAXXAIR_SKIP_PREFLIGHT=true`

## Package layout

```
maxxair_fan/
  main.py          Control loop, preflight, Firebase patch logic
  fan.py           Speed curve and IR filename resolution
  sensor.py        DS18B20 reading with CRC retry
  firebase.py      REST GET/PATCH helpers
  config.py        Environment-based settings
  cli.py           Subcommands (run, check, simulate, …)
  backends/        Pi, remote-agent, and fake implementations
  devtools/        Fake Firebase HTTP server and live TUI
ir_codes/          Recorded MaxxAir IR signals
firmware/          AtomS3 Lite edge-agent firmware
scripts/ir_to_rmt.py  Compile `.ir` files to ESP32 PROGMEM arrays
config/examples/   Hub JSON registries (including hub-atoms3.json)
tests/             Unit and integration tests
```

## Related docs

- [Topologies](topologies.md) — local Pi, hub + remote Pi, hub + AtomS3 Lite
- [Firebase schema](firebase-schema.md) — fields written to RTDB
- [CLI reference](cli.md) — run, check, simulate, replay
- [AtomS3 Lite agents](atoms3-agent.md) — hub + three Atom edge devices
- [Development](development.md) — fake backends and replay fixtures
