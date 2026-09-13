# AtomS3 Lite edge agents

Keep Python as the brain. Deploy **three** [M5Stack AtomS3 Lite](https://shop.m5stack.com/products/atoms3-lite-esp32s3-dev-kit) kits (SKU C124) as drop-in replacements for remote Pi agents — **one Atom per MaxxAir fan**. Each unit is an ESP32-S3FN8 with a built-in IR transmitter on GPIO 4.

The hub still runs `maxxair-fan run` on an always-on host (Pi, NAS, Home Assistant box, etc.). The Atoms do **not** talk to Firebase. They only implement the existing remote-agent HTTP API: `GET /health`, `GET /temp`, `POST /ir`.

This is Topology 2 in [Topologies](topologies.md) with Atom hardware instead of remote Pis. Hub registry: [`config/examples/hub-atoms3.json`](../config/examples/hub-atoms3.json). Firmware: [`firmware/atoms3-agent/`](../firmware/atoms3-agent/).

```
Firebase RTDB  <-->  hub: maxxair-fan run
                         |  HTTP :8765
                         +--> AtomS3 Lite fan1 --IR GPIO4--> MaxxAir 1
                         |                     --DS18B20 G5
                         +--> AtomS3 Lite fan2 --IR GPIO4--> MaxxAir 2
                         |                     --DS18B20 G5
                         +--> AtomS3 Lite fan3 --IR GPIO4--> MaxxAir 3
                                               --DS18B20 G5
```

Identities (mDNS, port **8765**):

- `http://maxxair-fan1.local:8765`
- `http://maxxair-fan2.local:8765`
- `http://maxxair-fan3.local:8765`

Shared `AGENT_TOKEN` (or per-fan override in hub JSON). Deduping IR still happens on the hub; each Atom just plays the filename it is sent.

## What you need per fan

- One AtomS3 Lite
- One DS18B20
- 4.7 kΩ resistor (pull-up to **3.3 V**)
- USB-C 5 V power
- Line of sight from the Atom's IR LED to the MaxxAir receiver

Do **not** add a discrete IR LED. The onboard emitter is the transmitter.

Rated operating range is **0–40 °C**. Mount the Atom in the living space aimed at the vent, not in a roof cavity.

## Pinout

| Function | Pin | Notes |
| --- | --- | --- |
| IR TX | GPIO 4 | Onboard IR LED, 40 kHz raw |
| DS18B20 data | GPIO 5 (G5) | Bottom header |
| DS18B20 power | 3V3 | Bottom header, **not** Grove 5 V |
| DS18B20 GND | GND | Bottom header |
| Status LED | GPIO 35 | WS2812C (firmware drives 4 pixels; official board LED is under the button) |
| Button | GPIO 41 | Click sends `fan_off.ir` |

Grove HY2.0-4P is `GND / 5V / G2 / G1`. The Grove port has no 3.3 V pin. ESP32-S3 GPIOs are not 5 V tolerant — do not pull the 1-wire line up to Grove 5 V. Grove G2/G1 stays free.

Confirm the 3.3 V pin against the [AtomS3-Lite schematic](https://docs.m5stack.com/en/core/AtomS3%20Lite) before soldering a harness.

### DS18B20 wiring

1. DS18B20 VDD → Atom 3V3
2. DS18B20 GND → Atom GND
3. DS18B20 DQ → G5
4. 4.7 kΩ between DQ and 3V3

Firmware calls `pinMode(G5, INPUT)` after `M5.begin()` and before `sensors.begin()` (otherwise reads return −127 °C). Conversion is ~750 ms. Failed CRC/disconnect retries three times, then `GET /temp` returns 503.

## Flash

Install [PlatformIO Core](https://platformio.org/install/cli). Copy secrets and set Wi-Fi plus the **same** bearer token the hub uses as `AGENT_TOKEN`:

```bash
cd firmware/atoms3-agent
cp src/secrets.h.example src/secrets.h
# edit WIFI_SSID, WIFI_PASSWORD, AGENT_TOKEN
```

Same firmware image on all three units; only the PlatformIO env identity differs (`maxxair-fan1` / `fan2` / `fan3`).

Put the Atom in download mode: hold reset about 2 seconds until the internal green LED lights, then release. USB Serial/JTAG — no CP2102 driver.

```bash
pio run -e fan1 -t upload   # maxxair-fan1.local
pio run -e fan2 -t upload   # maxxair-fan2.local
pio run -e fan3 -t upload   # maxxair-fan3.local
```

`pio run` regenerates `src/ir_timings.h` from [`ir_codes/`](../ir_codes/) via [`scripts/ir_to_rmt.py`](../scripts/ir_to_rmt.py) (PROGMEM microsecond mark/space arrays, 40 kHz carrier). Regenerate by hand:

```bash
python3 scripts/ir_to_rmt.py
```

Serial monitor: `pio device monitor -e fan1` (115200 baud, USB CDC).

## HTTP contract

Listen port **8765**. When `AGENT_TOKEN` is set, `/temp` and `/ir` require `Authorization: Bearer <token>`. `/health` is open.

| Method | Path | Body / response |
| --- | --- | --- |
| GET | `/health` | `{"ok": true}` |
| GET | `/temp` | `{"temp_f": 72.5}` or 503 |
| POST | `/ir` | `{"filename": "fan_on_in_40.ir"}` → 200, 400 unknown file, or 500 send fail |

IR path: `pinMode(4, OUTPUT)` then Arduino-IRremote `sendRaw` at 40 kHz. MaxxAir codes are raw pulse/space, not NEC.

Manual IR check (aim at the fan first):

```bash
curl -H "Authorization: Bearer your_shared_secret" \
  -H "Content-Type: application/json" \
  -d '{"filename":"fan_off.ir"}' \
  http://maxxair-fan1.local:8765/ir
```

If mDNS fails, use the IP printed on the serial console.

The Lite spec sheet does not quote IR distance. **Validate `fan_off.ir` against the nearest MaxxAir before placing the other two units.** Re-aim if the fan does not respond; keep the IR window unobstructed.

## Hub

On the always-on host that runs Python, `.env`:

```bash
FIREBASE_URL=https://your-project-rtdb.firebaseio.com
FIREBASE_SECRET=your_secret
FANS_CONFIG=/home/pi/maxxair-fan-pi-interface/config/examples/hub-atoms3.json
AGENT_TOKEN=your_shared_secret
```

Hub JSON:

```json
{
  "fans": [
    {"id": "fan1", "firebase_node": "fans/fan1", "agent_url": "http://maxxair-fan1.local:8765"},
    {"id": "fan2", "firebase_node": "fans/fan2", "agent_url": "http://maxxair-fan2.local:8765"},
    {"id": "fan3", "firebase_node": "fans/fan3", "agent_url": "http://maxxair-fan3.local:8765"}
  ]
}
```

The hub does not need local `ir-ctl` or a DS18B20. `maxxair-fan check` health-checks the three agents.

```bash
maxxair-fan check
maxxair-fan run --once
maxxair-fan run
```

Remote HTTP timeout is 5 seconds ([`RemoteAgentBackend`](../maxxair_fan/backends/remote_agent.py)) to cover DS18B20 conversion plus IR.

## Status LED and IR contention

| Color | Meaning |
| --- | --- |
| Dim white | Boot |
| Orange | Wi-Fi down / connecting |
| Green | Idle, Wi-Fi up |
| Blue | Sending IR |
| Red | Sensor failure |

IR uses LEDC PWM (`SEND_PWM_BY_TIMER`) so the WS2812C RMT driver does not collide with transmit. LED updates happen before and after `POST /ir`, never during.

## What this is not

- Not a replacement for `maxxair-fan run` on the Atom (no Linux, no `ir-ctl`, no Firebase client)
- Not one board for three fans
- Not a discrete IR LED circuit

## Related

- [Topologies](topologies.md) — hub + remote agents
- [Configuration](configuration.md) — `FANS_CONFIG`, `AGENT_TOKEN`
- [Troubleshooting](troubleshooting.md#atoms3-lite-agent)
