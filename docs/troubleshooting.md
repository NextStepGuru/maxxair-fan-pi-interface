# Troubleshooting

Symptoms, likely causes, and fixes. Run diagnostics first:

```bash
maxxair-fan check
maxxair-fan dump-state
```

On a Pi with systemd: `journalctl -u maxxair-fan -f`

## Sensor not found

**Symptoms:** `check` fails on sensor; `sensorOk: false` in Firebase; logs mention missing `28-*` device.

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

3. Check RTDB security rules allow the Pi to write. See [Firebase schema → Security rules](firebase-schema.md#security-rules).

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

## Getting help

Include output from:

```bash
maxxair-fan check
maxxair-fan dump-state
```

Redact `FIREBASE_SECRET` before sharing. See [CONTRIBUTING](../CONTRIBUTING.md) for pull request guidelines.
