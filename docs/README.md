# Documentation

Guides for installing, configuring, and developing the MaxxAir Fan Pi Interface.

## Start here

| Guide | What you'll learn |
| --- | --- |
| [Quickstart](quickstart.md) | Install on a Raspberry Pi, configure Firebase, and run the daemon |
| [Architecture](architecture.md) | Control loop, fan speed algorithm, backends, and data flow |
| [Configuration](configuration.md) | Every environment variable and tuning option |
| [CLI reference](cli.md) | All `maxxair-fan` subcommands with examples |
| [Firebase schema](firebase-schema.md) | RTDB fields, example document, and security rules |
| [Troubleshooting](troubleshooting.md) | Common problems and how to fix them |
| [Development](development.md) | Run locally without Pi hardware, replay fixtures, fake Firebase |
| [Topologies](topologies.md) | Multi-fan deployments: single Pi, hub + remote, multi-local |

## Other resources

| Document | Purpose |
| --- | --- |
| [README](../README.md) | Project overview and quick links |
| [CONTRIBUTING](../CONTRIBUTING.md) | How to run tests, lint, and submit changes |
| [CHANGELOG](../CHANGELOG.md) | Version history |
| [SECURITY](../SECURITY.md) | Reporting vulnerabilities and handling secrets |
| [`.env.example`](../.env.example) | Annotated configuration template |

## Typical paths

**Deploy on a Pi**

1. [Quickstart](quickstart.md) → configure [Firebase schema](firebase-schema.md) → run `maxxair-fan check`
2. If something fails → [Troubleshooting](troubleshooting.md)

**Tune fan behavior**

1. [Architecture → Fan speed curve](architecture.md#fan-speed-curve) → [Configuration → curve tuning](configuration.md#fan-speed-curve)
2. Preview changes with `maxxair-fan simulate` → [CLI reference](cli.md#simulate)

**Develop without hardware**

1. [Development](development.md) → `./scripts/dev.sh` or `--simulator` mode
2. Add scenarios with [replay fixtures](development.md#replay-fixtures)
