# Quickstart

Get the MaxxAir fan controller running on a Raspberry Pi.

## Prerequisites

- Raspberry Pi with network access
- [DS18B20](https://www.maximintegrated.com/en/products/sensors/DS18B20.html) temperature sensor on the 1-wire bus
- IR LED or blaster that works with Linux `ir-ctl` (v4l2 IR)
- MaxxAir roof vent fan (IR codes are included in [`ir_codes/`](../ir_codes/))
- Firebase Realtime Database project with a database secret

See [Architecture](architecture.md) for a diagram of how these pieces connect.

## 1. Enable 1-wire

Add to `/boot/firmware/config.txt` (Bookworm) or `/boot/config.txt` (older OS):

```
dtoverlay=w1-gpio
```

Reboot, then confirm the sensor appears:

```bash
ls /sys/bus/w1/devices/28-*
```

You should see a path like `28-000000c0959a`. If not, see [Troubleshooting → Sensor not found](troubleshooting.md#sensor-not-found).

## 2. Install system packages

```bash
sudo apt update
sudo apt install -y v4l-utils python3-pip python3-venv
```

Verify IR tooling:

```bash
which ir-ctl
ls /dev/lirc0
```

## 3. Clone and install

```bash
git clone https://github.com/NextStepGuru/maxxair-fan-pi-interface.git
cd maxxair-fan-pi-interface
./scripts/install.sh
```

`install.sh` creates a virtualenv, installs dependencies, and copies [`.env.example`](../.env.example) to `.env` if missing.

## 4. Configure Firebase

Edit `.env`:

```bash
FIREBASE_URL=https://your-project-rtdb.firebaseio.com
FIREBASE_SECRET=your_database_secret
FAN_NODE=fans/fan1
```

Set up your Firebase node with at least `targetTemp` and `direction`. See [Firebase schema](firebase-schema.md) for the full field list and sample security rules.

> **Security:** Never commit `.env`. Rotate your database secret if it is ever exposed. See [SECURITY.md](../SECURITY.md).

## 5. Preflight check

```bash
.venv/bin/python -m maxxair_fan check
```

This validates Firebase connectivity, sensor access, IR directory, and `ir-ctl` availability. Fix any `FAIL:` lines before continuing.

## 6. Test IR manually

```bash
ir-ctl -s ir_codes/fan_off.ir
```

The fan should respond. If not, see [Troubleshooting → IR not working](troubleshooting.md#ir-not-working).

## 7. Run the daemon

One-shot (single loop iteration):

```bash
.venv/bin/python -m maxxair_fan run --once
```

Continuous control loop:

```bash
.venv/bin/python -m maxxair_fan run
```

Or, after `pip install -e .`:

```bash
maxxair-fan run
```

The legacy entry point `python3 ir.py` still works but `maxxair-fan` is preferred.

## 8. Run as a systemd service (optional)

```bash
./scripts/install.sh --systemd
sudo systemctl start maxxair-fan
journalctl -u maxxair-fan -f
```

The unit file lives at [`deploy/maxxair-fan.service`](../deploy/maxxair-fan.service). `install.sh --systemd` rewrites paths to match your clone location.

## Next steps

- Tune the fan curve: [Configuration → Fan speed curve](configuration.md#fan-speed-curve)
- Explore CLI tools: [CLI reference](cli.md)
- Develop without a Pi: [Development](development.md)
