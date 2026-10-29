# MaxxAir Fan Pi Interface

**Created by [Ryder Henry](https://github.com/NextStepGuru/maxxair-fan-pi-interface).**

A thermostat daemon for MaxxAir roof vent fans, running on the coach's edge Raspberry Pi. The [coach Pi](docs/coach-network.md) (`192.168.10.126`) is the brain (Abbey: database and control). This Pi (`192.168.10.73`) handles local hardware: fan IR, the battery bank, and the USB-RS485 and USB-CAN adapters plugged into it.

The fan hub reads target temperature and direction from Firebase Realtime Database, computes fan speed with Ryder Henry's exponential curve, and sends IR commands — locally via `ir-ctl` on a Raspberry Pi, or over HTTP to remote agents (Raspberry Pi or [AtomS3 Lite](docs/atoms3-agent.md)).

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
| [Topologies](docs/topologies.md) | Single Pi, hub + remote, three AtomS3 Lite agents |
| [Coach network](docs/coach-network.md) | Coach Pi is the brain; this Pi is the edge for fans, batteries, RS485, and CAN |
| [AtomS3 Lite agents](docs/atoms3-agent.md) | Flash three Atoms as IR + DS18B20 edge agents |

## Quick start

```bash
git clone https://github.com/NextStepGuru/maxxair-fan-pi-interface.git
cd maxxair-fan-pi-interface
./scripts/install.sh
# Edit .env with FIREBASE_URL and FIREBASE_SECRET
maxxair-fan check
maxxair-fan run
```

Hardware setup (1-wire, IR blaster) and systemd install: [Quickstart](docs/quickstart.md). Three-fan AtomS3 Lite agents (hub Python + onboard IR): [AtomS3 Lite](docs/atoms3-agent.md).

## How it works

1. Read `targetTemp` and `direction` (`in` / `out`) from Firebase
2. Read current temperature from a DS18B20 (local 1-wire or remote agent)
3. Compute fan speed (0–100% in 10% steps) using the exponential algorithm
4. Send the matching pre-recorded IR code to the fan (local `ir-ctl` or remote agent)
5. Write status telemetry back to Firebase

Details and diagrams: [Architecture](docs/architecture.md).

## Requirements

**Local Pi (one host does everything)**

- Raspberry Pi with network access
- DS18B20 on the 1-wire bus
- IR LED / blaster compatible with Linux v4l2 IR (`ir-ctl`)

**Hub + AtomS3 Lite agents (three fans)**

- Always-on host to run `maxxair-fan run` (Pi or any machine with Python 3.11+)
- One [AtomS3 Lite](docs/atoms3-agent.md) per fan (onboard IR + DS18B20 on G5)

**Always**

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
