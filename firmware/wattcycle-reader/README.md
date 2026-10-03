# WattCycle BLE battery reader (ESP32-S3)

Standalone ESP32-S3 firmware that reads the six 48V WattCycle batteries
(bat01..bat06) over Bluetooth LE and publishes Victron-style retained topics
to the coach broker:

```
N/wattcycle48ble/battery/<1..6>/<Path>   payload {"value": <n>}   retained
```

Topics follow the same shape as the CAN pack feed (`N/wattcycle48/`, see
`maxxair_fan/wattcycle.py`) but use a distinct portal id so the two feeds
never collide. Abbey does not ingest `wattcycle48ble` yet — `lib/wattcycle.ts`
is hardcoded to the single `wattcycle48` portal.

## Protocol (XDZN TDT, current firmware generation)

Reverse-engineered from the WattCycle APK by the community
(github `qume/wattcycle_ble`, `PROTOCOL.md`; also
`frabnet/esphome-wattcycle-ble`, `ioBroker/ioBroker.wattcycle`):

1. Connect (no pairing/bonding), subscribe to `FFF1` (notify).
2. Write `HiLink` to `FFFA` (auth — flips a readable 0→1 state register).
3. Write TDT read frames to `FFF2` **without response**:
   `[head][0x00][0x01][0x03][dp:2][0x0000][crc16-modbus BE][0x0d]`
   - **Frame head is `0x7E` on current packs**; `0x1E` only on older batches
     (firmware tries 0x7E then falls back).
   - DPs: `0x008C` analog (cell volts, temps, current, capacity, SOC, SOH),
     `0x0092` product info (model/manufacturer/serial), `0x008D` warning info.
4. Responses arrive as notifications on `FFF1`; total length = payload_len + 11,
   payload at offset 8.

The six packs are 16S (48V), model `1001_10016SW17L0831`, 100Ah each.

## Hardware

- Board: ESP32-S3 devkit (N16R8, 16MB flash / 8MB PSRAM), MAC `94:a9:90:d1:7a:b4`
- No extra hardware needed (BLE is on-chip). Powered from the Maxxair Pi's USB.
- Battery MACs (from the WattCycle app): bat01 `c0:d6:3c:5f:4e:08`,
  bat02 `c0:d6:3c:5e:21:b0`, bat03 `c0:d6:3c:5f:68:a9`, bat04 `c0:d6:3c:5f:69:50`,
  bat05 `c0:d6:3c:5e:20:50`, bat06 `c0:d6:3c:5f:66:60`.

## Build / deploy

The board lives on the Maxxair Pi's USB (`/dev/ttyUSB0`, CP2102 port); builds
happen on the Mac and flash remotely:

```sh
pio run -e wattcycle-reader                                    # build
cd .pio/build/wattcycle-reader
scp bootloader.bin partitions.bin firmware.bin maxxair:wattcycle-flash/
ssh maxxair '~/.venvs/esptool/bin/esptool --port /dev/ttyUSB0 --baud 460800 \
  write_flash 0x0 bootloader.bin 0x8000 partitions.bin 0x10000 firmware.bin'
ssh maxxair '~/.venvs/esptool/bin/python ~/wattcycle-flash/monitor.py /dev/ttyUSB0 60'
```

## Envs

- `reader-a` (default): board A, packs 1-3.
- `reader-b`: board B, packs 4-6 (start staggered 12s to split airtime).
- `pylon-can`: receive-only Pylontech-CAN reader via TWAI (kept as a fallback
  for the CAN pack feed; needs an SN65HVD230 on GPIO4/5).
- `ble-scan`, `ble-probe`, `bleonly`: diagnostics used to reverse the GATT
  layout.

## Victron (Cerbo) feed

The ESPs publish only to the coach broker. A relay on this Pi
(`wattcycle-ble-relay.service`, `~/wattcycle-relay/wattcycle-ble-relay.py`)
subscribes to `N/wattcycle48ble/battery/+/+` and republishes one
venus-os_dbus-mqtt-battery JSON object per pack to the Cerbo broker
(192.168.10.127) on `wattcycle48ble/bat01..06`. Six driver instances
(`/data/etc/dbus-mqtt-battery-bat01..06`, device instances 101-106) turn
those into com.victronenergy.battery devices, so the GX (and Abbey's Victron
view) see each pack individually. Charge limits are static 16S LiFePO4
values (56.0V / 100A / 100A / 44.8V), mirroring the CAN pack feed.

## Known quirks

- BLE connects flake ~30% per round at the Pi's distance; each battery is
  retried and every pack reads successfully at least every other round
  (~2 min worst case). Abbey marks the feed stale after 3 minutes, so a
  missed round does not trip it.
- These packs advertise only ~1 name in 2 scan responses; the reader matches
  by MAC, so it is unaffected.
