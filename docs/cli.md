# CLI Reference

Entry points:

```bash
python -m maxxair_fan <command> [options]
maxxair-fan <command> [options]    # after pip install -e .
```

Run `maxxair-fan --help` or `maxxair-fan <command> --help` for built-in usage text.

## run

Run the control loop (continuous by default).

```bash
maxxair-fan run
maxxair-fan run --once
maxxair-fan run --simulator --tui
```

| Flag | Description |
| --- | --- |
| `--simulator` | Use fake sensor, fake IR, and in-memory Firebase |
| `--once` | Run one iteration and exit (skips flock lock) |
| `--tui` | Live status line on stderr |

**Examples**

```bash
# Production on Pi
maxxair-fan run

# Single iteration for testing
maxxair-fan run --once

# Local dev with live status
maxxair-fan run --simulator --tui
```

## check

Validate runtime prerequisites without starting the loop.

```bash
maxxair-fan check
```

Checks Firebase connectivity, sensor path, IR directory, and `ir-ctl`. Exits `0` with `OK:` or `1` with `FAIL:` lines on stderr.

Run this after [Quickstart](quickstart.md) configuration and before enabling systemd.

## send-ir

Send a single IR code file (uses configured `IR_BACKEND`).

```bash
maxxair-fan send-ir fan_off.ir
maxxair-fan send-ir fan_on_in_50.ir
```

Useful to verify hardware independently of the control loop. See [Troubleshooting → IR not working](troubleshooting.md#ir-not-working).

## simulate

Compute fan speed and IR filename without hardware or Firebase.

```bash
maxxair-fan simulate --temp 73.5 --target 72.0
maxxair-fan simulate --temp 74.0 --target 72.0 --direction out --gradient 0.5 --exponent 2.0
```

| Flag | Default | Description |
| --- | --- | --- |
| `--temp` | *(required)* | Current temperature °F |
| `--target` | `72.0` | Target temperature °F |
| `--direction` | `in` | `in` or `out` |
| `--gradient` | from config | `GRADIENT_DEGREES` override |
| `--exponent` | from config | `EXPONENT_VALUE` override |

Prints resolved speed, IR filename, and a sample curve table.

## replay

Replay a temperature time series through the control loop using fake backends.

```bash
maxxair-fan replay tests/fixtures/heating_up.json
maxxair-fan replay tests/fixtures/cooling_below.json --rate 2.0
maxxair-fan replay tests/fixtures/heating_up.json --expect expected_ir.json
```

| Flag | Default | Description |
| --- | --- | --- |
| `fixture` | *(required)* | JSON file with `target`, `direction`, `steps` |
| `--rate` | `1.0` | Time acceleration factor |
| `--expect` | unset | JSON file listing expected IR commands; exit 1 on mismatch |

Fixture format:

```json
{
  "target": 72.0,
  "direction": "in",
  "steps": [
    { "temp": 72.0 },
    { "temp": 72.8 },
    { "temp": 73.5 }
  ]
}
```

See [Development → Replay fixtures](development.md#replay-fixtures).

## dump-state

Print resolved configuration and runtime hints.

```bash
maxxair-fan dump-state
```

Shows backend selection, Firebase URL, paths, IR file count, and lock file status. Helpful when debugging [configuration](configuration.md) issues.

## Legacy entry point

`python3 ir.py` remains supported for backward compatibility. Prefer `maxxair-fan run` for new deployments.
