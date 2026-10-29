from maxxair_fan.wattcycle import CERBO_TOPIC, INVERTER_FRAMES, cerbo_payload, decode_pack, topic_for


def test_decodes_a_pylontech_cycle():
    frames = {
        0x351: bytes.fromhex("30 02 E8 03 E8 03 C0 01"),
        0x355: bytes.fromhex("60 00 64 00 00 00 00 00"),
        0x356: bytes.fromhex("C8 14 14 00 E9 00 00 00"),
        0x359: bytes.fromhex("00 00 00 00 01 50 4E 00"),
        0x35C: bytes.fromhex("C0 00 00 00 00 00 00 00"),
        0x35E: b"PYLO\x00\x00\x00\x00",
        0x373: bytes.fromhex("FC 0C 01 0D 28 01 28 01"),
        0x379: bytes.fromhex("64 00 00 00 00 00 00 00"),
    }
    values = decode_pack(frames)
    assert values["Soc"] == 96
    assert values["Soh"] == 100
    assert values["Dc/0/Voltage"] == 53.20
    assert values["Dc/0/Current"] == 2.0
    assert values["Dc/0/Temperature"] == 23.3
    assert values["Capacity"] == 100
    assert values["Info/ModuleCount"] == 1
    assert values["Info/ChargeRequest"] == 1
    assert values["Info/DischargeRequest"] == 1
    assert values["Info/MaxChargeVoltage"] == 56.0
    assert values["Info/BatteryLowVoltage"] == 44.8
    assert values["System/MinCellVoltage"] == 3.324
    assert values["System/MaxCellVoltage"] == 3.329
    assert values["System/MinCellTemperature"] == 23
    assert values["System/MaxCellTemperature"] == 23
    assert values["ProductName"] == "PYLO"
    assert values["Alarms/Alarm"] == 0


def test_revov_name_comes_from_the_name_frames():
    frames = {
        0x355: bytes.fromhex("64 00 64 00 10 27 00 00"),
        0x356: bytes.fromhex("9A 15 05 00 D7 00 00 00"),
        0x370: bytes.fromhex("52 65 76 6F 76 20 42 61"),
        0x371: bytes.fromhex("74 74 65 72 79 20 20 20"),
    }
    values = decode_pack(frames)
    assert values["CustomName"] == "Revov Battery"
    assert values["Soc"] == 100
    assert values["Dc/0/Voltage"] == 55.30
    assert values["Dc/0/Current"] == 0.5
    assert values["Dc/0/Temperature"] == 21.5


def test_topic_uses_the_wattcycle_portal():
    assert topic_for("Soc") == "N/wattcycle48/battery/1/Soc"
    assert CERBO_TOPIC == "wattcycle48"


def test_cerbo_payload_omits_flags_the_bus_did_not_send():
    frames = {
        0x351: bytes.fromhex("30 02 00 00 D0 07 C0 01"),
        0x355: bytes.fromhex("64 00 64 00 10 27 00 00"),
        0x356: bytes.fromhex("9A 15 05 00 D7 00 00 00"),
        0x370: bytes.fromhex("52 65 76 6F 76 20 42 61"),
        0x371: bytes.fromhex("74 74 65 72 79 20 20 20"),
    }
    payload = cerbo_payload(decode_pack(frames), frames)
    assert payload["InstalledCapacity"] == 600
    assert payload["Soc"] == 100
    assert "Soh" not in payload
    assert payload["Dc"] == {
        "Power": round(55.30 * 0.5, 1),
        "Voltage": 55.30,
        "Current": 0.5,
        "Temperature": 21.5,
    }
    assert payload["Info"] == {
        "MaxChargeVoltage": 56.0,
        "MaxChargeCurrent": 0.0,
        "MaxDischargeCurrent": 200.0,
    }
    assert "Io" not in payload
    assert "Alarms" not in payload
    assert "System" not in payload
    assert "Capacity" not in payload


def test_cerbo_payload_includes_flags_cells_and_alarms_when_present():
    frames = {
        0x351: bytes.fromhex("30 02 E8 03 E8 03 C0 01"),
        0x355: bytes.fromhex("60 00 64 00 00 00 00 00"),
        0x356: bytes.fromhex("C8 14 14 00 E9 00 00 00"),
        0x359: bytes.fromhex("02 01 04 00 01 50 4E 00"),
        0x35C: bytes.fromhex("C0 00 00 00 00 00 00 00"),
        0x373: bytes.fromhex("FC 0C 01 0D 28 01 28 01"),
        0x379: bytes.fromhex("64 00 00 00 00 00 00 00"),
    }
    payload = cerbo_payload(decode_pack(frames), frames)
    assert payload["Io"] == {"AllowToCharge": 1, "AllowToDischarge": 1}
    assert payload["System"]["MinCellVoltage"] == 3.324
    assert payload["System"]["MaxCellVoltage"] == 3.329
    assert payload["Alarms"]["HighVoltage"] == 2
    assert payload["Alarms"]["HighChargeCurrent"] == 2
    assert payload["Alarms"]["LowVoltage"] == 1
    assert payload["InstalledCapacity"] == 600
    assert "Capacity" not in payload


def test_inverter_presence_is_the_pylon_keepalive():
    assert INVERTER_FRAMES == (
        (0x305, bytes.fromhex("3002e803e803c001")),
        (0x307, bytes.fromhex("1234567856494300")),
    )
