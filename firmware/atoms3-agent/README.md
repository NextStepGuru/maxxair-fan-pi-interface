# AtomS3 Lite edge agent

Firmware for [M5Stack AtomS3 Lite](https://shop.m5stack.com/products/atoms3-lite-esp32s3-dev-kit) units that expose the MaxxAir remote-agent HTTP API (`GET /health`, `GET /temp`, `POST /ir`).

One Atom per fan. Python on a hub still owns Firebase and the speed curve.

```bash
cp src/secrets.h.example src/secrets.h   # WIFI_SSID, WIFI_PASSWORD, AGENT_TOKEN
# download mode: hold reset ~2s until green LED
pio run -e fan1 -t upload   # maxxair-fan1.local
pio run -e fan2 -t upload
pio run -e fan3 -t upload
```

Pins: IR GPIO 4, DS18B20 G5 (3.3 V + 4.7 kΩ pull-up), status WS2812C GPIO 35.

Full wiring, flash, mDNS, and hub `.env`: [docs/atoms3-agent.md](../../docs/atoms3-agent.md).
