# Firebase Realtime Database Schema

The Pi daemon reads user settings and writes status telemetry to a single RTDB node.

**Node path:** `fans/fan1` (override with `FAN_NODE` — see [Configuration](configuration.md#firebase))

## Example document

```json
{
  "targetTemp": 72.0,
  "direction": "in",
  "currentTemp": 73.4,
  "lastUpdate": "2026-05-25T20:00:00+00:00",
  "online": true,
  "sensorOk": true,
  "irOk": true,
  "lastIrCommand": "fan_on_in_40.ir",
  "lastError": null,
  "sensorCrcFailures": 0
}
```

## Fields

### User / app writes

These fields control fan behavior. Your mobile app or dashboard should write them.

| Field | Type | Description |
| --- | --- | --- |
| `targetTemp` | number | Desired temperature in °F |
| `direction` | string | `"in"` (intake) or `"out"` (exhaust) |

### Pi writes

The daemon updates these on each loop (subject to [write throttling](configuration.md#firebase-write-throttling)).

| Field | Type | Description |
| --- | --- | --- |
| `currentTemp` | number | Latest sensor reading; omitted when sensor read fails |
| `lastUpdate` | string | ISO 8601 UTC timestamp of last status write |
| `online` | boolean | `true` while daemon is running and publishing |
| `sensorOk` | boolean | `false` when DS18B20 read fails |
| `irOk` | boolean | `false` when last IR send attempt failed |
| `lastIrCommand` | string | Last IR filename sent (e.g. `fan_on_in_40.ir`) |
| `lastError` | string \| null | Human-readable error, or `null` when clear |
| `sensorCrcFailures` | number | Cumulative DS18B20 CRC failures since daemon start |

## Read / write summary

| Field | Written by |
| --- | --- |
| `targetTemp`, `direction` | User / app |
| All other fields | Pi daemon |

## Security rules

Sample rules allowing public read and authenticated write:

```json
{
  "rules": {
    "fans": {
      "fan1": {
        ".read": true,
        ".write": "auth != null"
      }
    }
  }
}
```

Adjust for your deployment:

- The **Pi** needs write access (via legacy database secret or auth token)
- **Clients** need read access for telemetry and write access for `targetTemp` / `direction`
- Restrict paths to the minimum required (e.g. per-fan nodes)

The Pi authenticates with `FIREBASE_SECRET` using `?auth=` on REST requests. See [SECURITY.md](../SECURITY.md) for secret handling and migration notes.

## Related

- [Configuration → Firebase](configuration.md#firebase)
- [Architecture → Control loop](architecture.md#control-loop)
- [Troubleshooting → Firebase errors](troubleshooting.md#firebase-401--connection-errors)
