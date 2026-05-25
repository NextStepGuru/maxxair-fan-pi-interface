# Multi-Fan Topologies

The central daemon (`maxxair-fan run`) controls one or more fans per loop tick. Each fan is defined in a JSON registry (`FANS_CONFIG`) or via legacy single-fan environment variables.

## Topology 1: One fan, one Pi

The default deployment. Use legacy env vars or a single-entry JSON config.

```bash
# Legacy (no FANS_CONFIG)
FAN_NODE=fans/fan1
# SENSOR_PATH and IR_DEVICE optional

maxxair-fan run
```

Or with explicit registry:

```bash
FANS_CONFIG=/home/pi/maxxair-fan-pi-interface/config/examples/single-local.json
maxxair-fan run
```

See [`config/examples/single-local.json`](../config/examples/single-local.json).

## Topology 2: Hub Pi + remote fan Pis

A central Pi runs the daemon with **no local fans**. Each remote Pi runs an edge agent that exposes sensor + IR over HTTP.

**Hub Pi** (`.env`):

```bash
FIREBASE_URL=https://your-project-rtdb.firebaseio.com
FIREBASE_SECRET=your_secret
FANS_CONFIG=/home/pi/maxxair-fan-pi-interface/config/examples/hub-remote.json
AGENT_TOKEN=your_shared_secret
```

**Each remote Pi** (`.env`):

```bash
AGENT_BIND=0.0.0.0
AGENT_PORT=8765
AGENT_TOKEN=your_shared_secret
SENSOR_PATH=/sys/bus/w1/devices/28-xxx/w1_slave
IR_DEVICE=/dev/lirc0
```

Install and start the agent on each remote Pi:

```bash
sudo cp deploy/maxxair-fan-agent.service /etc/systemd/system/
sudo systemctl enable --now maxxair-fan-agent
```

Start the central daemon on the hub:

```bash
sudo systemctl enable --now maxxair-fan
```

See [`config/examples/hub-remote.json`](../config/examples/hub-remote.json).

## Topology 3: Multiple fans on one Pi

One Pi with multiple DS18B20 sensors and IR blasters. Each fan needs a distinct `sensor_path` and `ir_device`.

```bash
FANS_CONFIG=/home/pi/maxxair-fan-pi-interface/config/examples/multi-local.json
maxxair-fan run
```

See [`config/examples/multi-local.json`](../config/examples/multi-local.json).

## JSON registry schema

```json
{
  "fans": [
    {
      "id": "fan1",
      "firebase_node": "fans/fan1",
      "local": {
        "sensor_path": "/sys/bus/w1/devices/28-abc/w1_slave",
        "ir_device": "/dev/lirc0"
      }
    },
    {
      "id": "fan2",
      "firebase_node": "fans/fan2",
      "agent_url": "http://pi2.local:8765",
      "agent_token": "optional-per-fan-override"
    }
  ]
}
```

| Field | Required | Description |
| --- | --- | --- |
| `id` | yes | Unique fan identifier (logging) |
| `firebase_node` | yes | RTDB path for config and telemetry |
| `local` | one of | Local sensor + IR on the central Pi |
| `agent_url` | one of | HTTP base URL of remote edge agent |
| `agent_token` | no | Per-fan bearer token (overrides `AGENT_TOKEN`) |

Each fan must have exactly one of `local` or `agent_url`.

## Edge agent API

Run with `maxxair-fan agent` on remote Pis.

| Method | Path | Description |
| --- | --- | --- |
| GET | `/health` | Liveness check |
| GET | `/temp` | Returns `{"temp_f": 72.5}` |
| POST | `/ir` | Body `{"filename": "fan_on_in_50.ir"}` |

When `AGENT_TOKEN` is set, requests must include `Authorization: Bearer <token>` (except `/health`).

## Firebase nodes

Create one RTDB node per fan (e.g. `fans/fan1`, `fans/fan2`, `fans/fan3`). Each node uses the same schema documented in [Firebase schema](firebase-schema.md).

## Related docs

- [Configuration](configuration.md) — environment variables
- [Architecture](architecture.md) — control loop details
- [CLI reference](cli.md) — `run`, `agent`, `check`
