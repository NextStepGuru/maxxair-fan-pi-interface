# Troubleshooting

Symptoms, likely causes, and fixes. Run diagnostics first:

```bash
maxxair-fan check
maxxair-fan dump-state
```

On a Pi with systemd: `journalctl -u maxxair-fan -f`

Using AtomS3 Lite agents: [AtomS3 Lite agent](#atoms3-lite-agent) and [AtomS3 Lite agents](atoms3-agent.md).

## Sensor not found

**Symptoms:** `check` fails on sensor; `sensorOk: false` in Firebase; logs mention missing `28-*` device.

For remote AtomS3 agents this section does not apply — see [AtomS3 Lite agent](#atoms3-lite-agent).

**Fixes**

1. Enable 1-wire in `/boot/firmware/config.txt` (or `/boot/config.txt`):

   ```
   dtoverlay=w1-gpio
   ```

2. Reboot and verify:

   ```bash
   ls /sys/bus/w1/devices/28-*
   ```

3. If multiple sensors exist, set the correct one in `.env`:

   ```bash
   SENSOR_PATH=/sys/bus/w1/devices/28-000000c0959a/w1_slave
   ```

4. Check wiring (data pin, 4.7kΩ pull-up, 3.3V and GND).

CRC failures increment `sensorCrcFailures` in Firebase. The daemon retries reads automatically.

## IR not working

**Symptoms:** Fan does not respond; `irOk: false`; `lastError` mentions IR or `ir-ctl`.

For AtomS3 onboard IR, skip `ir-ctl` / `/dev/lirc0` and use [AtomS3 Lite agent](#atoms3-lite-agent).

**Fixes**

1. Confirm tooling and device:

   ```bash
   which ir-ctl
   ls -l /dev/lirc0
   ```

2. Test manually:

   ```bash
   ir-ctl -s ir_codes/fan_off.ir
   maxxair-fan send-ir fan_off.ir
   ```

3. Add your user to `video` and `gpio` groups (required by systemd unit):

   ```bash
   sudo usermod -aG video,gpio pi
   ```

4. Verify `IR_DIR` points to the directory with `.ir` files (`maxxair-fan dump-state`).

5. Re-record IR codes if your remote differs from the bundled set.

## Firebase 401 / connection errors

**Symptoms:** `check` fails on Firebase; logs show HTTP 401 or connection refused.

**Fixes**

1. Verify `.env` values:

   ```bash
   FIREBASE_URL=https://your-project-rtdb.firebaseio.com
   FIREBASE_SECRET=your_database_secret
   ```

2. Confirm the secret matches Firebase Console → Realtime Database → Rules / legacy secret.

3. Check RTDB security rules allow the hub to write. See [Firebase schema → Security rules](firebase-schema.md#security-rules).

4. Test with curl:

   ```bash
   curl "$FIREBASE_URL/$FAN_NODE.json?auth=$FIREBASE_SECRET"
   ```

> This project uses the legacy database secret (`?auth=`). See [SECURITY.md](../SECURITY.md) for migration guidance.

## Preflight fails

**Symptoms:** Daemon exits on startup; `check` prints one or more `FAIL:` lines.

**Fixes**

1. Run `maxxair-fan check` and address each failure individually.

2. For temporary bypass (not recommended on Pi):

   ```bash
   MAXXAIR_SKIP_PREFLIGHT=true maxxair-fan run
   ```

## Fan stuck at wrong speed

**Symptoms:** Firebase shows correct target but fan speed does not match; repeated IR in logs.

**Fixes**

1. Check `lastIrCommand` and `irOk` in Firebase.

2. Look for IR send errors in logs. Failed sends retry on the next loop iteration.

3. Confirm direction matches (`in` vs `out` use different IR files).

4. Preview expected behavior:

   ```bash
   maxxair-fan simulate --temp <current> --target <target> --direction in
   ```

5. IR deduplication skips identical consecutive commands — a speed change requires a different `.ir` file.

## Daemon won't start / already running

**Symptoms:** "Another instance is running" or immediate exit.

**Fixes**

1. Check lock file (default `/tmp/maxxair-fan.lock`):

   ```bash
   maxxair-fan dump-state
   cat /tmp/maxxair-fan.lock
   ```

2. Stop the other process or remove stale lock if no process holds it:

   ```bash
   sudo systemctl stop maxxair-fan
   ```

## systemd service issues

**Symptoms:** Service fails or restarts repeatedly.

**Fixes**

1. View logs:

   ```bash
   journalctl -u maxxair-fan -n 50 --no-pager
   ```

2. Confirm paths in the unit match your install (`WorkingDirectory`, `EnvironmentFile`, `ExecStart`).

3. Re-run `./scripts/install.sh --systemd` after moving the repo.

4. Test manually as the service user:

   ```bash
   sudo -u pi bash -c 'cd /home/pi/maxxair-fan-pi-interface && .venv/bin/python -m maxxair_fan check'
   ```

## AtomS3 Lite agent

**Symptoms:** Hub `check` fails on agent health; `sensorOk`/`irOk` false for a remote fan; Atom LED stays orange or red.

**Fixes**

1. Confirm the unit joined Wi-Fi: serial console should print an IP and `http://<name>-maxxair-fan.local:8765`. Orange LED means Wi-Fi is down.

2. Test the HTTP contract:

   ```bash
   curl http://simon-maxxair-fan.local:8765/health
   curl -H "Authorization: Bearer $AGENT_TOKEN" http://simon-maxxair-fan.local:8765/temp
   curl -H "Authorization: Bearer $AGENT_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"filename":"fan_off.ir"}' \
     http://simon-maxxair-fan.local:8765/ir
   ```

3. DS18B20 reads of −127 °C / 503: `pinMode(G5, INPUT)` must run after `M5.begin()`. Check 3.3 V power and the 4.7 kΩ pull-up to 3.3 V, not 5 V.

4. Fan ignores IR: aim GPIO 4's IR window at the MaxxAir receiver from inside the cabin. The Lite's IR range is unpublished — confirm `fan_off.ir` before placing the other units.

5. Flash: hold reset ~2 s until the green LED lights, then `pio run -e fan1 -t upload`. See [AtomS3 Lite agents](atoms3-agent.md).

## Getting help

Include output from:

```bash
maxxair-fan check
maxxair-fan dump-state
```

Redact `FIREBASE_SECRET` before sharing. See [CONTRIBUTING](../CONTRIBUTING.md) for pull request guidelines.
