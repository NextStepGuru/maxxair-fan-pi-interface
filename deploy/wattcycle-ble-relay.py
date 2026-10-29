#!/usr/bin/env python3
"""Relay WattCycle BLE battery topics to the Cerbo's dbus-mqtt-battery driver.

Subscribes to the coach broker (N/wattcycle48ble/battery/<n>/...) and
publishes to the Cerbo broker:
  - one aggregated bank object on wattcycle48ble/bank (all six packs as
    modules: NrOfModulesOnline/Offline, bank-wide cell min/max)
  - per-pack objects on wattcycle48ble/bat01..06 (kept for drill-down;
    their driver instances are parked by default)

Same JSON schema the CAN pack feed uses (maxxair_fan/wattcycle.py).
"""

from __future__ import annotations

import json
import threading
import time

import paho.mqtt.client as mqtt

COACH_HOST = "192.168.10.126"
CERBO_HOST = "192.168.10.127"
PORT = 1883
TOPIC_FILTER = "N/wattcycle48ble/battery/#"
BANK_TOPIC = "wattcycle48ble/bank"
PER_PACK_PREFIX = "wattcycle48ble/bat0"
PACK_COUNT = 6
HEARTBEAT_S = 30.0
FRESH_S = 180.0
BANK_CAPACITY_AH = 600.0  # 6 x 100Ah
PACK_CAPACITY_AH = 100.0

# Victron 16S LiFePO4 limits, mirroring what the packs advertise on the
# Pylontech CAN bus (Info/Max* on the CAN feed).
STATIC_INFO = {
    "MaxChargeVoltage": 56.0,
    "MaxChargeCurrent": 100.0,
    "MaxDischargeCurrent": 100.0,
    "BatteryLowVoltage": 44.8,
}

fields: dict[int, dict[str, object]] = {n: {} for n in range(1, PACK_COUNT + 1)}
updated_at: dict[int, float] = {n: 0.0 for n in range(1, PACK_COUNT + 1)}
last_pack_pub: dict[int, float] = {n: 0.0 for n in range(1, PACK_COUNT + 1)}
last_bank_pub = 0.0
lock = threading.Lock()

coach: mqtt.Client
cerbo: mqtt.Client


def as_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def on_coach_message(_c: mqtt.Client, _u, msg: mqtt.MQTTMessage) -> None:
    parts = msg.topic.split("/")
    # path segments after the battery number rejoin: Dc/0/Voltage etc.
    if len(parts) < 5 or parts[2] != "battery":
        return
    try:
        n = int(parts[3])
    except ValueError:
        return
    if not 1 <= n <= PACK_COUNT:
        return
    path = "/".join(parts[4:])
    try:
        payload = json.loads(msg.payload)
    except json.JSONDecodeError:
        return
    value = payload.get("value") if isinstance(payload, dict) else payload
    with lock:
        fields[n][path] = value
        updated_at[n] = time.monotonic()


def num(f: dict[str, object], key: str) -> float | None:
    return as_number(f.get(key))


def build_pack_payload(n: int) -> dict | None:
    with lock:
        f = dict(fields[n])
    voltage = num(f, "Dc/0/Voltage")
    if voltage is None:
        return None
    dc: dict[str, object] = {"Voltage": voltage}
    current = num(f, "Dc/0/Current")
    if current is not None:
        dc["Current"] = current
        dc["Power"] = round(voltage * current, 1)
    mos = num(f, "Dc/0/Temperature")
    if mos is not None:
        dc["Temperature"] = mos
    payload: dict[str, object] = {"Dc": dc, "InstalledCapacity": PACK_CAPACITY_AH}
    soc = num(f, "Soc")
    if soc is not None:
        payload["Soc"] = soc
    payload["Info"] = dict(STATIC_INFO)
    system: dict[str, object] = {}
    for src, name in (
        ("System/MinCellVoltage", "MinCellVoltage"),
        ("System/MaxCellVoltage", "MaxCellVoltage"),
    ):
        v = num(f, src)
        if v is not None:
            system[name] = v
    temps = f.get("System/CellTemps")
    if isinstance(temps, list) and temps:
        numbers = [t for t in (as_number(x) for x in temps) if t is not None]
        if numbers:
            system["MinCellTemperature"] = min(numbers)
            system["MaxCellTemperature"] = max(numbers)
    mos_v = num(f, "Dc/0/Temperature")
    if "MinCellTemperature" not in system and mos_v is not None:
        system["MinCellTemperature"] = mos_v
        system["MaxCellTemperature"] = mos_v
    if system:
        payload["System"] = system
    payload["Io"] = {"AllowToCharge": 1, "AllowToDischarge": 1}
    payload["Alarms"] = {"Alarm": 0}
    name = f.get("CustomName") or f.get("ProductName")
    if isinstance(name, str) and name:
        payload["ProductName"] = name
        payload["CustomName"] = name
    return payload


def build_bank_payload() -> dict | None:
    with lock:
        packs = [dict(fields[n]) for n in range(1, PACK_COUNT + 1)
                 if time.monotonic() - updated_at[n] < FRESH_S]
    online = len(packs)
    if online == 0:
        return None
    voltages = [v for v in (num(f, "Dc/0/Voltage") for f in packs) if v is not None]
    if not voltages:
        return None
    currents = [c for c in (num(f, "Dc/0/Current") for f in packs) if c is not None]
    socs = [s for s in (num(f, "Soc") for f in packs) if s is not None]
    dc: dict[str, object] = {
        "Voltage": round(sum(voltages) / len(voltages), 2),
        "Power": 0.0,
    }
    if currents:
        total_current = round(sum(currents), 1)
        dc["Current"] = total_current
        dc["Power"] = round(dc["Voltage"] * total_current, 1)
    payload: dict[str, object] = {
        "Dc": dc,
        "InstalledCapacity": BANK_CAPACITY_AH,
        "Soc": round(sum(socs) / len(socs), 1) if socs else None,
        "Info": {
            "MaxChargeVoltage": STATIC_INFO["MaxChargeVoltage"],
            "MaxChargeCurrent": STATIC_INFO["MaxChargeCurrent"] * online,
            "MaxDischargeCurrent": STATIC_INFO["MaxDischargeCurrent"] * online,
            "BatteryLowVoltage": STATIC_INFO["BatteryLowVoltage"],
        },
        "System": {
            "NrOfModulesOnline": online,
            "NrOfModulesOffline": PACK_COUNT - online,
            "NrOfCellsPerBattery": 16,
        },
        "Io": {"AllowToCharge": 1, "AllowToDischarge": 1},
        "Alarms": {"Alarm": 0},
        "ProductName": "WattCycle rack",
        "CustomName": "WattCycle rack",
    }
    if payload["Soc"] is None:
        payload.pop("Soc")
    mins = [num(f, "System/MinCellVoltage") for f in packs]
    maxs = [num(f, "System/MaxCellVoltage") for f in packs]
    mins = [v for v in mins if v is not None]
    maxs = [v for v in maxs if v is not None]
    if mins:
        payload["System"]["MinCellVoltage"] = min(mins)
    if maxs:
        payload["System"]["MaxCellVoltage"] = max(maxs)
    temps: list[float] = []
    for f in packs:
        cell_temps = f.get("System/CellTemps")
        if isinstance(cell_temps, list):
            temps.extend(t for t in (as_number(x) for x in cell_temps) if t is not None)
        mos = num(f, "Dc/0/Temperature")
        if mos is not None:
            temps.append(mos)
    if temps:
        payload["System"]["MinCellTemperature"] = min(temps)
        payload["System"]["MaxCellTemperature"] = max(temps)
    return payload


def connected_cerbo() -> bool:
    return cerbo.is_connected()


def safe_publish(topic: str, payload: dict) -> bool:
    try:
        info = cerbo.publish(topic, json.dumps(payload), retain=True)
        if info.rc != 0:
            raise OSError(f"publish rc={info.rc}")
        return True
    except Exception as exc:
        print(f"publish {topic} failed: {exc}", flush=True)
        try:
            cerbo.reconnect()
        except Exception:
            pass
        return False


def publish_loop() -> None:
    global last_bank_pub
    while True:
        now = time.monotonic()
        with lock:
            fresh = [n for n in range(1, PACK_COUNT + 1)
                     if now - updated_at[n] < FRESH_S]
        for n in fresh:
            first = last_pack_pub[n] == 0.0
            payload = build_pack_payload(n)
            if payload is None:
                continue
            if first or now - last_pack_pub[n] >= HEARTBEAT_S:
                if safe_publish(f"{PER_PACK_PREFIX}{n}", payload):
                    last_pack_pub[n] = now
        if now - last_bank_pub >= HEARTBEAT_S:
            bank = build_bank_payload()
            if bank is not None and safe_publish(BANK_TOPIC, bank):
                last_bank_pub = now
                print(f"bank: {bank['System']['NrOfModulesOnline']}/{PACK_COUNT} online, "
                      f"{bank['Dc']['Voltage']}V soc={bank.get('Soc')}", flush=True)
        time.sleep(5)


def main() -> None:
    global coach, cerbo
    coach = mqtt.Client(client_id="wattcycle48ble-relay-coach")
    cerbo = mqtt.Client(client_id="wattcycle48ble-relay-cerbo")
    coach.on_message = on_coach_message
    coach.connect(COACH_HOST, PORT, 60)
    coach.subscribe(TOPIC_FILTER, qos=0)
    cerbo.connect(CERBO_HOST, PORT, 60)
    print(
        f"relay up: {COACH_HOST} {TOPIC_FILTER} -> {CERBO_HOST} "
        f"{BANK_TOPIC} + {PER_PACK_PREFIX}1..{PACK_COUNT}",
        flush=True,
    )
    threading.Thread(target=publish_loop, daemon=True).start()
    coach.loop_forever()


if __name__ == "__main__":
    main()
