"""Pylontech (PY) CAN from the WattCycle pack.

The coach broker gets Victron-style topics under portal id ``wattcycle48``.
The Cerbo at 192.168.10.127 gets one JSON object on topic ``wattcycle48`` for
venus-os_dbus-mqtt-battery. The two feeds stay separate.
"""

from __future__ import annotations

import json
import socket
import struct
import subprocess
import time
from collections.abc import Mapping

PORTAL_ID = "wattcycle48"
INSTANCE = 1
BROKER_HOST = "192.168.10.126"
BROKER_PORT = 1883
CERBO_HOST = "192.168.10.127"
CERBO_TOPIC = "wattcycle48"
INSTALLED_CAPACITY_AH = 600

PY_IDS = (0x351, 0x355, 0x356, 0x359, 0x35A, 0x35C, 0x35E, 0x370, 0x371, 0x373, 0x379)

# 0x305 is the inverter presence frame, sent every second. Official Pylon
# uses eight zero bytes. This pack stopped after one burst until it sees a
# non-zero charge voltage there, so the bytes mirror the limits it already
# advertised: 56.0 V, 100 A charge, 100 A discharge, 44.8 V. 0x307 is the
# documented trigger for the extra frames (cell min/max, capacity).
# 0x1001 and 0x4800 are not sent: those arm a shutdown.
INVERTER_FRAMES = (
    (0x305, bytes.fromhex("3002e803e803c001")),
    (0x307, bytes.fromhex("1234567856494300")),
)

_CAN_FRAME = struct.Struct("=IB3x8s")


def u16(data: bytes, index: int) -> int:
    return data[index] | (data[index + 1] << 8)


def s16(data: bytes, index: int) -> int:
    value = u16(data, index)
    return value - 65536 if value >= 32768 else value


def _name(data: bytes) -> str:
    return data.split(b"\x00", 1)[0].decode("ascii", "replace").strip()


def decode_pack(frames: Mapping[int, bytes]) -> dict[str, object]:
    """Turn one PY cycle into coach topic values. Missing frames are omitted."""
    out: dict[str, object] = {
        "ProductName": "PYLO",
        "CustomName": "WattCycle",
        "Connected": 1,
    }
    limits = frames.get(0x351)
    if limits and len(limits) >= 8:
        out["Info/MaxChargeVoltage"] = u16(limits, 0) / 10
        out["Info/MaxChargeCurrent"] = u16(limits, 2) / 10
        out["Info/MaxDischargeCurrent"] = u16(limits, 4) / 10
        out["Info/BatteryLowVoltage"] = u16(limits, 6) / 10
    soc = frames.get(0x355)
    if soc and len(soc) >= 4:
        out["Soc"] = u16(soc, 0)
        out["Soh"] = u16(soc, 2)
    measurement = frames.get(0x356)
    if measurement and len(measurement) >= 6:
        out["Dc/0/Voltage"] = u16(measurement, 0) / 100
        out["Dc/0/Current"] = s16(measurement, 2) / 10
        out["Dc/0/Temperature"] = s16(measurement, 4) / 10
    status = frames.get(0x359)
    if status and len(status) >= 5:
        out["Info/ModuleCount"] = status[4]
        out["Alarms/Alarm"] = 1 if status[0] or status[1] or status[2] or status[3] else 0
    flags = frames.get(0x35C)
    if flags and len(flags) >= 1:
        out["Info/ChargeRequest"] = 1 if flags[0] & 0x80 else 0
        out["Info/DischargeRequest"] = 1 if flags[0] & 0x40 else 0
    name_parts = frames.get(0x370, b"") + frames.get(0x371, b"")
    if name_parts:
        text = _name(name_parts)
        if text:
            out["ProductName"] = text
            out["CustomName"] = text
    name = frames.get(0x35E)
    if name:
        text = _name(name)
        if text:
            out["ProductName"] = text
    cells = frames.get(0x373)
    if cells and len(cells) >= 8 and (u16(cells, 0) or u16(cells, 2)):
        out["System/MinCellVoltage"] = u16(cells, 0) / 1000
        out["System/MaxCellVoltage"] = u16(cells, 2) / 1000
        # Pylon 0x373 temperatures are Kelvin, not tenths of a degree.
        out["System/MinCellTemperature"] = u16(cells, 4) - 273
        out["System/MaxCellTemperature"] = u16(cells, 6) - 273
    capacity = frames.get(0x379)
    if capacity and len(capacity) >= 2:
        out["Capacity"] = u16(capacity, 0)
    return out


def topic_for(path: str) -> str:
    return f"N/{PORTAL_ID}/battery/{INSTANCE}/{path}"


def _bit(value: int, bit: int) -> bool:
    return bool(value & (1 << bit))


def _alarm_level(protection: bool, warning: bool) -> int:
    if protection:
        return 2
    if warning:
        return 1
    return 0


def _pylon_alarms(status: bytes) -> dict[str, int]:
    """Map Pylon 0x359 protection (level 2) and warning (level 1) bits."""
    protect = status[0]
    protect_extra = status[1]
    warning = status[2]
    return {
        "HighVoltage": _alarm_level(_bit(protect, 1), _bit(warning, 1)),
        "LowVoltage": _alarm_level(_bit(protect, 2), _bit(warning, 2)),
        "HighTemperature": _alarm_level(_bit(protect, 3), _bit(warning, 3)),
        "LowTemperature": _alarm_level(_bit(protect, 4), _bit(warning, 4)),
        "HighDischargeCurrent": _alarm_level(_bit(protect, 7), _bit(warning, 7)),
        "HighChargeCurrent": _alarm_level(_bit(protect_extra, 0), False),
    }


def cerbo_payload(
    values: Mapping[str, object], frames: Mapping[int, bytes] | None = None
) -> dict[str, object]:
    """One bank object for venus-os_dbus-mqtt-battery. Missing frames stay omitted."""
    voltage = values.get("Dc/0/Voltage")
    current = values.get("Dc/0/Current")
    dc: dict[str, object] = {}
    if isinstance(voltage, (int, float)) and isinstance(current, (int, float)):
        dc["Power"] = round(float(voltage) * float(current), 1)
    if isinstance(voltage, (int, float)):
        dc["Voltage"] = voltage
    if isinstance(current, (int, float)):
        dc["Current"] = current
    temperature = values.get("Dc/0/Temperature")
    if isinstance(temperature, (int, float)):
        dc["Temperature"] = temperature
    payload: dict[str, object] = {"Dc": dc, "InstalledCapacity": INSTALLED_CAPACITY_AH}
    if "Soc" in values:
        payload["Soc"] = values["Soc"]
    info: dict[str, object] = {}
    for source, name in (
        ("Info/MaxChargeVoltage", "MaxChargeVoltage"),
        ("Info/MaxChargeCurrent", "MaxChargeCurrent"),
        ("Info/MaxDischargeCurrent", "MaxDischargeCurrent"),
    ):
        if source in values:
            info[name] = values[source]
    if info:
        payload["Info"] = info
    system: dict[str, object] = {}
    for source, name in (
        ("System/MinCellVoltage", "MinCellVoltage"),
        ("System/MaxCellVoltage", "MaxCellVoltage"),
        ("System/MinCellTemperature", "MinCellTemperature"),
        ("System/MaxCellTemperature", "MaxCellTemperature"),
    ):
        if source in values:
            system[name] = values[source]
    if system:
        payload["System"] = system
    if "Info/ChargeRequest" in values or "Info/DischargeRequest" in values:
        io: dict[str, object] = {}
        if "Info/ChargeRequest" in values:
            io["AllowToCharge"] = values["Info/ChargeRequest"]
        if "Info/DischargeRequest" in values:
            io["AllowToDischarge"] = values["Info/DischargeRequest"]
        payload["Io"] = io
    status = None if frames is None else frames.get(0x359)
    if status is not None and len(status) >= 4:
        payload["Alarms"] = _pylon_alarms(status)
    return payload


class _Broker:
    """Minimal MQTT 3.1.1 publisher. Publishes are retained."""

    def __init__(self, host: str, port: int, client_id: bytes) -> None:
        self.host = host
        self.port = port
        self._client_id = client_id
        self._sock: socket.socket | None = None

    def publish(self, topic: str, payload: str) -> None:
        sock = self._ensure()
        topic_b = topic.encode()
        body = bytes([0, len(topic_b)]) + topic_b + payload.encode()
        try:
            sock.sendall(_packet(0x31, body))
        except OSError:
            self.close()
            raise

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def _ensure(self) -> socket.socket:
        if self._sock is not None:
            return self._sock
        sock = socket.create_connection((self.host, self.port), timeout=8)
        sock.settimeout(8)
        client_id = self._client_id
        packet = (
            b"\x00\x04MQTT"
            b"\x04\x02\x00\x3c"
            + bytes([0, len(client_id)])
            + client_id
        )
        sock.sendall(_packet(0x10, packet))
        ack = _read_packet(sock)
        if not ack or ack[0] != 0x20:
            sock.close()
            raise ConnectionError(f"{self.host} rejected the connection")
        self._sock = sock
        return sock


class CoachPublisher:
    """Victron-style topics on the coach broker. Retained messages survive an Abbey restart."""

    def __init__(self, host: str = BROKER_HOST, port: int = BROKER_PORT) -> None:
        self._broker = _Broker(host, port, b"wattcycle48")

    def publish(self, values: Mapping[str, object]) -> None:
        for path, value in values.items():
            self._broker.publish(topic_for(path), json.dumps({"value": value}))

    def close(self) -> None:
        self._broker.close()


class CerboPublisher:
    """One JSON battery object on the Cerbo broker."""

    def __init__(self, host: str = CERBO_HOST, port: int = BROKER_PORT) -> None:
        self._broker = _Broker(host, port, b"wattcycle-cerbo")

    def publish(self, payload: Mapping[str, object]) -> None:
        self._broker.publish(CERBO_TOPIC, json.dumps(payload, separators=(",", ":")))

    def close(self) -> None:
        self._broker.close()


def _packet(header: int, body: bytes) -> bytes:
    remaining = _varint(len(body))
    return bytes([header]) + remaining + body


def _varint(length: int) -> bytes:
    out = bytearray()
    while True:
        digit = length % 128
        length //= 128
        if length:
            digit |= 0x80
        out.append(digit)
        if not length:
            return bytes(out)


def _read_packet(sock: socket.socket) -> bytes:
    head = sock.recv(1)
    if not head:
        return b""
    length = 0
    shift = 0
    while True:
        digit = sock.recv(1)
        if not digit:
            return b""
        value = digit[0]
        length += (value & 0x7F) << shift
        if not value & 0x80:
            break
        shift += 7
    body = b""
    while len(body) < length:
        chunk = sock.recv(length - len(body))
        if not chunk:
            break
        body += chunk
    return head + body


def ensure_can() -> None:
    if subprocess.call(["ip", "link", "show", "can0"], stdout=subprocess.DEVNULL) == 0:
        subprocess.check_call(["ip", "link", "set", "can0", "up"])
        return
    subprocess.check_call(["slcand", "-o", "-s6", "/dev/canable", "can0"])
    time.sleep(0.4)
    subprocess.check_call(["ip", "link", "set", "can0", "type", "can", "bitrate", "500000"])
    subprocess.check_call(["ip", "link", "set", "can0", "up"])


def open_can() -> socket.socket:
    sock = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
    sock.bind(("can0",))
    sock.settimeout(1.0)
    return sock


def write_frame(sock: socket.socket, can_id: int, data: bytes) -> None:
    sock.send(_CAN_FRAME.pack(can_id, 8, data[:8].ljust(8, b"\x00")))


def read_frame(sock: socket.socket) -> tuple[int, bytes] | None:
    try:
        raw = sock.recv(_CAN_FRAME.size)
    except TimeoutError:
        return None
    if len(raw) < _CAN_FRAME.size:
        return None
    can_id, length, data = _CAN_FRAME.unpack(raw)
    return can_id & 0x7FF, data[:length]


def _publish_bank(publisher: CoachPublisher | CerboPublisher, payload: Mapping[str, object], label: str) -> bool:
    try:
        publisher.publish(payload)
    except OSError as exc:
        print(f"{label} publish failed: {exc}", flush=True)
        publisher.close()
        return False
    return True


def run() -> None:
    ensure_can()
    can = open_can()
    coach = CoachPublisher()
    cerbo = CerboPublisher()
    frames: dict[int, bytes] = {}
    last_values: dict[str, object] | None = None
    last_cerbo: dict[str, object] | None = None
    last_coach_at = 0.0
    last_cerbo_at = 0.0
    print(
        f"wattcycle listening on can0, publishing {PORTAL_ID} to {BROKER_HOST} and {CERBO_HOST}",
        flush=True,
    )
    while True:
        frame = read_frame(can)
        if frame is not None:
            can_id, data = frame
            if can_id in PY_IDS:
                frames[can_id] = data
        if not frames:
            continue
        now = time.monotonic()
        values = decode_pack(frames)
        bank = cerbo_payload(values, frames)
        # Republish a held value every 30 seconds so the coach trainer
        # and the Cerbo driver both treat the bank as fresh.
        if values != last_values or now - last_coach_at >= 30.0:
            if _publish_bank(coach, values, "coach"):
                last_values = values
                last_coach_at = now
        if bank != last_cerbo or now - last_cerbo_at >= 30.0:
            if _publish_bank(cerbo, bank, "cerbo"):
                last_cerbo = bank
                last_cerbo_at = now


if __name__ == "__main__":
    run()
