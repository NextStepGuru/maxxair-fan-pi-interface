# MaxxAir Fan Pi Interface

**Created by [Ryder Henry](https://github.com/NextStepGuru/maxxair-fan-pi-interface).**

A Raspberry Pi thermostat daemon for MaxxAir roof vent fans. Reads a DS18B20 temperature sensor, syncs target temperature and direction from Firebase Realtime Database, computes fan speed with Ryder Henry's exponential curve, and sends IR commands via `ir-ctl`.

## Documentation

| Guide | Description |
| --- | --- |
| [**Docs index**](docs/README.md) | Full table of contents |
| [Quickstart](docs/quickstart.md) | Pi install, Firebase setup, first run |
| [Architecture](docs/architecture.md) | Control loop, speed algorithm, backends |
| [Configuration](docs/configuration.md) | Environment variables reference |
| [CLI reference](docs/cli.md) | `run`, `check`, `simulate`, `replay`, … |
| [Firebase schema](docs/firebase-schema.md) | RTDB fields and security rules |
| [Troubleshooting](docs/troubleshooting.md) | Common issues and fixes |
| [Development](docs/development.md) | Local dev without Pi hardware |

## Quick start

```bash
git clone https://github.com/NextStepGuru/maxxair-fan-pi-interface.git
cd maxxair-fan-pi-interface
./scripts/install.sh
# Edit .env with FIREBASE_URL and FIREBASE_SECRET
maxxair-fan check
maxxair-fan run
```

Hardware setup (1-wire, IR blaster) and systemd install: [Quickstart](docs/quickstart.md).

## How it works

1. Read `targetTemp` and `direction` (`in` / `out`) from Firebase
2. Read current temperature from a DS18B20 1-wire sensor
3. Compute fan speed (0–100% in 10% steps) using the exponential algorithm
4. Send the matching pre-recorded IR code to the fan
5. Write status telemetry back to Firebase

Details and diagrams: [Architecture](docs/architecture.md).

## Requirements

- Raspberry Pi with network access
- DS18B20 on the 1-wire bus
- IR LED / blaster compatible with Linux v4l2 IR (`ir-ctl`)
- Firebase Realtime Database
- MaxxAir fan (IR codes in [`ir_codes/`](ir_codes/))

## CLI

```bash
maxxair-fan run              # control loop
maxxair-fan check            # preflight validation
maxxair-fan simulate --temp 73.5 --target 72.0
maxxair-fan run --simulator --tui   # local dev, no hardware
```

Full command reference: [CLI](docs/cli.md). Legacy entry point: `python3 ir.py`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Changelog: [CHANGELOG.md](CHANGELOG.md). Security: [SECURITY.md](SECURITY.md).

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE).
