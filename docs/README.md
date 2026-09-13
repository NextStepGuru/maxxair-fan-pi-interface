# Documentation

Guides for installing, configuring, and developing the MaxxAir fan controller (local Pi hardware or hub + AtomS3 Lite agents).

## Start here

| Guide | What you'll learn |
| --- | --- |
| [Quickstart](quickstart.md) | Install on a Raspberry Pi with local 1-wire + `ir-ctl` |
| [Architecture](architecture.md) | Control loop, fan speed algorithm, backends, and data flow |
| [Configuration](configuration.md) | Every environment variable and tuning option |
| [CLI reference](cli.md) | All `maxxair-fan` subcommands with examples |
| [Firebase schema](firebase-schema.md) | RTDB fields, example document, and security rules |
| [Troubleshooting](troubleshooting.md) | Common problems and how to fix them |
| [Development](development.md) | Run locally without Pi hardware, replay fixtures, fake Firebase |
| [Topologies](topologies.md) | Multi-fan deployments: single Pi, hub + remote Pi or AtomS3 Lite, multi-local |
| [AtomS3 Lite agents](atoms3-agent.md) | Flash three AtomS3 Lite units as IR + DS18B20 edge agents |

## Other resources

| Document | Purpose |
| --- | --- |
| [README](../README.md) | Project overview and quick links |
| [CONTRIBUTING](../CONTRIBUTING.md) | How to run tests, lint, and submit changes |
| [CHANGELOG](../CHANGELOG.md) | Version history |
| [SECURITY](../SECURITY.md) | Reporting vulnerabilities and handling secrets |
| [`.env.example`](../.env.example) | Annotated configuration template |

## Typical paths

**Deploy hub + three AtomS3 Lite agents**

1. [AtomS3 Lite agents](atoms3-agent.md) → flash fan1 and prove IR with `fan_off.ir` before placing fan2/fan3
2. Hub `.env` with `FANS_CONFIG=config/examples/hub-atoms3.json` → `maxxair-fan check` → `run --once`

**Deploy on a Pi (local sensor + IR)**

1. [Quickstart](quickstart.md) → configure [Firebase schema](firebase-schema.md) → run `maxxair-fan check`
2. If something fails → [Troubleshooting](troubleshooting.md)

**Tune fan behavior**

1. [Architecture → Fan speed curve](architecture.md#fan-speed-curve) → [Configuration → curve tuning](configuration.md#fan-speed-curve)
2. Preview changes with `maxxair-fan simulate` → [CLI reference](cli.md#simulate)

**Develop without hardware**

1. [Development](development.md) → `./scripts/dev.sh` or `--simulator` mode
2. Add scenarios with [replay fixtures](development.md#replay-fixtures)
