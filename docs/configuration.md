# Configuration

All settings are read from environment variables. The daemon loads a `.env` file in the repo root when `python-dotenv` is installed (included in requirements).

Copy [`.env.example`](../.env.example) to `.env` and edit before first run.

Print resolved values at any time:

```bash
maxxair-fan dump-state
```

## Firebase

| Variable | Default | Description |
| --- | --- | --- |
| `FIREBASE_URL` | *(required on Pi)* | Firebase RTDB base URL, e.g. `https://project-rtdb.firebaseio.com` |
| `FIREBASE_SECRET` | *(required on Pi)* | Database secret for `?auth=` REST authentication |
| `FAN_NODE` | `fans/fan1` | RTDB path for this fan's config and status |

See [Firebase schema](firebase-schema.md) for field definitions.

## Hardware paths

| Variable | Default | Description |
| --- | --- | --- |
| `IR_DIR` | `./ir_codes/` | Directory containing `.ir` code files |
| `SENSOR_PATH` | auto-detect | Full path to DS18B20 `w1_slave` file; first `28-*` device if unset |

## Control loop

| Variable | Default | Description |
| --- | --- | --- |
| `CHECK_INTERVAL` | `2` | Seconds between loop iterations (2 recommended for DS18B20 conversion) |
| `LOCK_FILE` | `/tmp/maxxair-fan.lock` | Single-instance flock lock path |
| `FAN_OFF_ON_EXIT` | `false` | Send `fan_off.ir` on graceful shutdown |
| `MAXXAIR_SKIP_PREFLIGHT` | `false` | Skip startup validation (not recommended on Pi) |
| `LOG_LEVEL` | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

## Fan speed curve

| Variable | Default | Description |
| --- | --- | --- |
| `GRADIENT_DEGREES` | `0.5` | Degrees above target per exponential step |
| `EXPONENT_VALUE` | `2.0` | Base for speed calculation |

Formula (when `current > target`):

```
speed = 10 × EXPONENT_VALUE^((diff / GRADIENT_DEGREES) - 1)
```

Result is rounded to 10% steps, max 100%. Preview with:

```bash
maxxair-fan simulate --temp 73.5 --target 72.0 --gradient 0.5 --exponent 2.0
```

See [Architecture → Fan speed curve](architecture.md#fan-speed-curve) for the default lookup table.

## Firebase write throttling

| Variable | Default | Description |
| --- | --- | --- |
| `TEMP_PATCH_THRESHOLD` | `0.1` | Minimum °F change before writing `currentTemp` |
| `PATCH_HEARTBEAT_SECONDS` | `60` | Max seconds between status patches regardless of temp change |

## Backends

Set `MAXXAIR_BACKEND=simulator` for local development, or override individual layers:

| Variable | Default | Values | Description |
| --- | --- | --- | --- |
| `MAXXAIR_BACKEND` | `pi` | `pi`, `simulator` | Preset for all backends |
| `SENSOR_BACKEND` | *(inherits)* | `w1`, `fake` | Temperature source |
| `IR_BACKEND` | *(inherits)* | `irctl`, `fake` | IR sender |
| `FIREBASE_BACKEND` | *(inherits)* | `rest`, `memory` | Firebase client |

### Simulator-only

| Variable | Default | Description |
| --- | --- | --- |
| `FAKE_SENSOR_TEMP` | `72.0` | Static temp (°F) or path to JSON temp series |
| `FAKE_IR_LOG` | unset | Append fake IR sends to this JSON log file |

Example simulator `.env` snippet:

```bash
MAXXAIR_BACKEND=simulator
SENSOR_BACKEND=fake
IR_BACKEND=fake
FIREBASE_BACKEND=memory
FAKE_SENSOR_TEMP=73.5
```

Or use CLI flags: `maxxair-fan run --simulator --once --tui`

See [Development](development.md) for `./scripts/dev.sh` and fake Firebase.

## systemd

When installed via `./scripts/install.sh --systemd`, the unit loads `.env` from the repo:

```
EnvironmentFile=/home/pi/maxxair-fan-pi-interface/.env
```

Edit paths in [`deploy/maxxair-fan.service`](../deploy/maxxair-fan.service) if your install location differs.
