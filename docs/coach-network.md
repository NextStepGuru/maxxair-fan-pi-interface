# Coach network

Checked on the hardware **2026-09-24**.

The coach Raspberry Pi is the brain: database and control center. Abbey (`abbey-nextstepguru`) runs there and is the system of record. This Maxxair Pi is an edge node. It owns local buses (fans, batteries, RS485, CAN) and reports to the coach. It does not keep the coach database.

```
Mac (deyoungjd)
  |  ssh coachproxy / ssh maxxair
  |
  +-- Coach Pi  192.168.10.126  coachproxyos   Raspberry Pi 4
  |     Abbey API :3000  (database / control center)
  |     ssh deyoungjd@192.168.10.73
  |
  +-- Maxxair Pi  192.168.10.73  pi-4-48volt   Raspberry Pi 5
        fans, batteries, other local sensors
        /dev/rs485   USB-RS485
        /dev/canable USB-CAN FD
        ssh deyoungjd@192.168.10.126
```

Other edge devices follow the same rule: talk to the coach Pi, do not become a second database.

## Machines

| Role | Host | Board | OS | Address | SSH |
| --- | --- | --- | --- | --- | --- |
| Brain | `coachproxyos` | Raspberry Pi 4 Model B Rev 1.4 | Debian 12 (bookworm) | `192.168.10.126` (Ethernet; Wi-Fi is also `192.168.10.122`) | `ssh deyoungjd@192.168.10.126` or `ssh coachproxy` |
| Edge | `pi-4-48volt` | Raspberry Pi 5 Model B Rev 1.1 | Debian 13 (trixie), kernel `6.18.50+rpt-rpi-2712` | `192.168.10.73` on Wi-Fi `old_devices_2g` | `ssh deyoungjd@192.168.10.73` or `ssh maxxair` |
| Fan agent 1 | `simon-maxxair-fan` | M5Stack AtomS3 Lite (ESP32-S3, MAC `e8:f6:0a:98:fe:94`) | `firmware/atoms3-agent` env `fan1` | `192.168.10.224` (DHCP reservation) on Wi-Fi `old_devices_2g`, HTTP `:8765` | none |
| Battery readers | `wattcycle-reader` a/b | 2× ESP32-S3 devkit N16R8 (board A `94:a9:90:d1:7a:b4` on ttyUSB0 packs 1-3, board B on ttyUSB1 packs 4-6, 12s stagger) | `firmware/wattcycle-reader` | USB on `pi-4-48volt` (power + flash), Wi-Fi `old_devices_2g`; publish `N/wattcycle48ble/battery/<1-6>/#` (six 48V WattCycle packs over BLE, per-pack 16-cell array) to the coach broker; see [README](../firmware/wattcycle-reader/README.md) | none |

The Atoms need a 2.4 GHz network, so they join `old_devices_2g`. Use their IPs in the hub fans config. `.local` names do not resolve on the Pis: the DNS search domain turns them into `<name>.local.home.nextstep.guru`, which Cloudflare answers.

The coach Pi cannot reach `old_devices_2g` directly (checked 2026-09-28: no ping, no TCP to `.224`, while `.73` answers fine). Abbey's fan commands therefore go through a socat relay on this Pi: `192.168.10.73:18765` → `192.168.10.224:8765`, installed as `fan-agent-relay-simon.service` ([unit file](../deploy/fan-agent-relay-simon.service)). Abbey sets `FAN_AGENT_SIMON_URL=http://192.168.10.73:18765`. Add one relay unit per Atom when alvin and theodore ship.

Abbey is checked out at `/coachproxy/home/pi/abbey-nextstepguru` on the coach Pi. `abbey-nextstepguru.service` is active. `http://192.168.10.126:3000/api/overview` answers (401 without the API key).

From this Mac, `~/.ssh/config` maps `coachproxy` → `192.168.10.126` and `maxxair` → `192.168.10.73`, user `deyoungjd`.

## Home LAN from the laptop

The Mac (`Jeremys-MBP-2`, Cloudflare device profile **Default**) can reach `192.168.10.0/24` whether it is on the coach Wi-Fi or not. WARP carries that subnet through the coach tunnel `abby-pi-01`. The rest of `192.168.0.0/16` stays off WARP. The local router `192.168.10.1` stays on the laptop's own interface so normal internet still uses the current network.

`ssh deyoungjd@192.168.10.126` and `ssh deyoungjd@192.168.10.73` are the commands. Checked 2026-09-25: both answered while the laptop was at home, and the route was the WARP interface (`utun`), not the Wi-Fi interface.

## WattCycle pack

The Maxxair Pi reads the WattCycle BMS on `/dev/canable` (Pylontech PY, 500 kbit/s, acknowledgements on) and publishes it to the coach broker `192.168.10.126:1883` as portal id `wattcycle48`:

`N/wattcycle48/battery/1/Soc`

That id is only this pack. Abbey subscribes to `N/wattcycle48/#` and puts the reading on the overview as `wattcycle`. The Victron GX batteries stay on their own portals.

## WattCycle BLE rack (six 48V packs)

Two ESP32-S3 boards (`firmware/wattcycle-reader`, envs `reader-a` packs 1-3 and
`reader-b` packs 4-6) read bat01-bat06 over BLE and publish
`N/wattcycle48ble/battery/<1-6>/#` to the coach broker, including the full
16-cell voltage array per pack (`System/Cells`) and cell temps. Protocol and
quirks are documented in the firmware [README](../firmware/wattcycle-reader/README.md).

`wattcycle-ble-relay.service` ([unit](../deploy/wattcycle-ble-relay.service),
[script](../deploy/wattcycle-ble-relay.py), installed at `~/wattcycle-relay/`
on this Pi) republishes to the Cerbo broker: a bank aggregate on
`wattcycle48ble/bank` (6 modules, 600Ah, bank SOC/voltage/current) plus
per-pack objects on `wattcycle48ble/bat01..06`. On the Cerbo,
`/data/etc/dbus-mqtt-battery-bank` (device instance 110) presents the bank as
the single **WattCycle rack** battery; the per-pack driver instances
(`/data/etc/dbus-mqtt-battery-bat01..06`) are parked (down files in
`/service/...`) and can be re-enabled for per-pack drill-down. Abbey renders
the rack with per-cell grids from the coach-broker topics
(`wattcycleBle` in the overview).

## Remote SSH

Each Pi also runs its own outbound Cloudflare Tunnel to localhost port 22. Nothing is listening on the public internet.

| From anywhere | Command | Tunnel |
| --- | --- | --- |
| Coach Pi | `ssh coach-ssh` | `coach-ssh.nextstepguru.com` |
| Maxxair Pi | `ssh maxxair-ssh` | `maxxair-ssh.nextstepguru.com` |

`coachproxy` and `maxxair` stay on the LAN. Each remote hostname has a Cloudflare Access application that allows `jeremy@nextstep.guru`. `cloudflared` opens a login before the SSH key is used.

## Logins

`deyoungjd`, `pi`, and `jeremy` are the same uid (`1000`) and the same password on both Pis. Passwordless sudo is on for all three. The password is not stored in git.

SSH is key-based in both directions and from this Mac. Each side's ed25519 key is in the other's `authorized_keys`, along with this Mac's RSA and ed25519 keys.

| From | Command |
| --- | --- |
| Mac → coach | `ssh deyoungjd@192.168.10.126` |
| Mac → Maxxair | `ssh deyoungjd@192.168.10.73` |
| Maxxair → coach | `ssh deyoungjd@192.168.10.126` |
| Coach → Maxxair | `ssh deyoungjd@192.168.10.73` |

`pi@` and `jeremy@` also work. They land in the same home as `deyoungjd` on the Maxxair Pi (`/home/deyoungjd`). On the coach Pi, `pi` and `jeremy` still have their own homes (`/coachproxy/home/pi` and `/home/jeremy`); `deyoungjd` is `/home/deyoungjd`.

## What this Pi does

1. **MaxxAir fans** — this repo. The hub reads target temperature and direction, computes speed, and sends IR. See [Architecture](architecture.md). Fan hardware (DS18B20, IR blaster) is **not** plugged into this Pi yet.
2. **New battery bank** — this Pi talks to the batteries. RS485 (Modbus) and CAN FD are the two buses. Readings belong in Abbey on the coach Pi, not in a private database here.
3. **Other local monitoring** — same pattern. Sense it here, report it to `192.168.10.126`.

## Plugged in right now

Checked again 2026-09-26: only the CANable is enumerated. `/dev/rs485` is not present. No 1-wire sensor, no `/dev/lirc*`. `can0` is up at 500 kbit/s while `wattcycle-bms` is running. `maxxair-fan` is not running.

| Stable path | Kernel | USB ID | What it is | State on 2026-09-24 |
| --- | --- | --- | --- | --- |
| `/dev/rs485` | `/dev/ttyUSB0` | `10c4:ea60` Silicon Labs CP2102 | [DSD TECH SH-U10](https://www.amazon.com/dp/B078X5H8H7) USB to RS485 | Not plugged in on 2026-09-26. On 2026-09-24 the port opened and the bus was silent. |
| `/dev/canable` | `/dev/ttyACM0` | `16d0:117e` MCS CANable2 | [Jhoinrch RH-02 PLUS](https://www.amazon.com/dp/B0F9F9J3WN) USB to CAN FD, CANable 2.0, slcan firmware | Driver `cdc_acm` loaded. `V\r` returns `16e7497-dirty github.com/normaldotcom/canable2.git`. Serial `207D3254594B`. |

By-id paths:

- `/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0`
- `/dev/serial/by-id/usb-Openlight_Labs_CANable2_b158aa7_github.com_normaldotcom_canable2.git_207D3254594B-if00`

`deyoungjd` is in `dialout`, so both nodes are `crw-rw---- root:dialout`. Stable names come from [`deploy/99-maxxair-usb.rules`](../deploy/99-maxxair-usb.rules), already installed at `/etc/udev/rules.d/99-maxxair-usb.rules`.

The CAN adapter is not RS232. There is no USB-RS232 device on this Pi.

### Battery on CAN

WattCycle **WT48V100AH100RACK-3UBT** (51.2 V 100 Ah rack pack). CAN is on the front **CAN/RS485 (LINK-IN/LINK-OUT)** RJ45, not the RS232 CONSOLE jack.

| RJ45 pin | Signal |
| --- | --- |
| 4 | CANH |
| 5 | CANL |
| 6 | GND |
| 1 and 8 | RS485-B |
| 2 and 7 | RS485-A |

Checked 2026-09-24 after the CAN adapter was cabled to the pack: `can0` comes up, but 500 kbit/s and 250 kbit/s both showed **0 frames and 0 bus errors**. The wire is quiet. The pack screen has to be on and an inverter protocol selected before it talks, and the plug has to be in the CAN/RS485 jack with pin 4 on CANH and pin 5 on CANL.

### RS485 (SH-U10)

Terminal block: **A+**, **B-**, **GND**, **GND**, **5V**. Leave 5V disconnected unless the far device needs power from the adapter. CP2102 needs no extra driver on this Pi.

Open check (expect silence until a meter is wired):

```bash
python3 -c "import os; os.open('/dev/rs485', os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK); print('rs485 open')"
```

### CAN FD (RH-02 PLUS / CANable 2)

The board enumerates as a serial slcan port, not as a SocketCAN `can0` device, until `slcand` is started. Do not send `O` (open bus) just to probe it.

Version check, 115200 8N1, command `V` then carriage return:

```bash
python3 - <<'PY'
import os, select, termios, time
fd = os.open("/dev/canable", os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
a = termios.tcgetattr(fd)
a[0] = a[1] = a[3] = 0
a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
a[4] = a[5] = termios.B115200
a[6][termios.VMIN] = a[6][termios.VTIME] = 0
termios.tcsetattr(fd, termios.TCSANOW, a)
os.write(fd, b"V\r")
end = time.time() + 0.8
buf = b""
while time.time() < end:
    r, _, _ = select.select([fd], [], [], 0.2)
    if r:
        buf += os.read(fd, 256)
os.close(fd)
print(buf)
PY
```

To use it as a normal CAN interface later (not enabled as a service yet):

```bash
sudo apt install -y can-utils
sudo slcand -o -c -s6 -S 115200 /dev/canable can0
sudo ip link set can0 up
```

`-s6` is 500 kbit/s. Match the battery bus speed before opening it.

## Not plugged in

- DS18B20 / 1-wire (`/sys/bus/w1/devices` is empty)
- IR blaster (`/dev/lirc*` missing, `ir-ctl` not in use)
- Battery wiring on RS485 A/B or the CAN H/L screw terminals
- A second USB-serial adapter (only these two)

I2C device nodes `/dev/i2c-13` and `/dev/i2c-14` are the Pi 5 controller, not an external sensor board.
