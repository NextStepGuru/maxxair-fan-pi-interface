# Development

Run and test the controller without Raspberry Pi hardware.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .
pre-commit install   # optional
```

See [CONTRIBUTING.md](../CONTRIBUTING.md) for test and lint commands.

## Quick local run

`./scripts/dev.sh` starts a fake Firebase server and runs the daemon in simulator mode with a live TUI:

```bash
./scripts/dev.sh
```

This sets:

- Fake Firebase at `http://localhost:9000` (UI in browser)
- `MAXXAIR_BACKEND=simulator` with fake sensor/IR
- Static fake temp of 73.5°F

## Simulator mode

Run manually without the dev script:

```bash
export MAXXAIR_BACKEND=simulator
export SENSOR_BACKEND=fake
export IR_BACKEND=fake
export FIREBASE_BACKEND=memory

maxxair-fan run --simulator --once --tui
maxxair-fan run --simulator --tui
```

Or use the CLI flag alone (uses in-memory Firebase with default fan node):

```bash
maxxair-fan run --simulator --once
```

### Fake Firebase HTTP server

Start the REST-compatible fake server for testing mobile apps or REST clients:

```bash
python -m maxxair_fan.devtools.fake_firebase --port 9000 --state .dev/firebase.json
```

Point `.env` at it:

```bash
FIREBASE_URL=http://localhost:9000
FIREBASE_BACKEND=rest
MAXXAIR_BACKEND=simulator
```

Browse state at `http://localhost:9000`.

## Simulate fan curve

No loop, no Firebase — just compute speed and IR file:

```bash
maxxair-fan simulate --temp 73.5 --target 72.0
maxxair-fan simulate --temp 74.0 --target 72.0 --direction out
```

See [CLI → simulate](cli.md#simulate).

## Replay fixtures

JSON fixtures drive fake sensor temps through the real control loop logic.

Existing fixtures in `tests/fixtures/`:

| File | Scenario |
| --- | --- |
| `heating_up.json` | Room warms above target, fan ramps up |
| `cooling_below.json` | Room at/below target, fan off |
| `direction_change.json` | Direction switch changes IR prefix |
| `noisy_sensor.json` | Sensor noise around threshold |

Run a replay:

```bash
maxxair-fan replay tests/fixtures/heating_up.json
maxxair-fan replay tests/fixtures/heating_up.json --rate 5.0
```

### Create a new fixture

1. Create `tests/fixtures/your_scenario.json`:

   ```json
   {
     "target": 72.0,
     "direction": "in",
     "steps": [
       { "temp": 72.0 },
       { "temp": 72.6 },
       { "temp": 73.2 }
     ]
   }
   ```

2. Replay and inspect IR commands printed at the end.

3. Optionally add `"expected_ir": ["fan_off.ir", "fan_on_in_10.ir"]` to the fixture and validate:

   ```bash
   maxxair-fan replay tests/fixtures/your_scenario.json --expect tests/fixtures/your_scenario.json
   ```

4. Add to `tests/integration/test_replay_fixtures.py` parametrize list for CI.

## Tests

```bash
pytest --cov=maxxair_fan --cov-report=term-missing
pytest -m "not integration"    # unit tests only
pytest -m integration          # integration tests only
```

## Lint

```bash
ruff check .
ruff format .
```

## Architecture for contributors

| Module | Role |
| --- | --- |
| `maxxair_fan/main.py` | Loop, preflight, Firebase patch logic |
| `maxxair_fan/fan.py` | Speed curve, IR filename resolution |
| `maxxair_fan/backends/` | Swappable Pi vs fake implementations |
| `maxxair_fan/devtools/` | Fake Firebase server, live TUI |

Read [Architecture](architecture.md) for the full data flow.

## Related

- [Configuration → Backends](configuration.md#backends)
- [CLI reference](cli.md)
- [CONTRIBUTING.md](../CONTRIBUTING.md)
