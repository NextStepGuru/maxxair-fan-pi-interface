from maxxair_fan import config, fan


def test_send_ir_without_device(mock_subprocess_run):
    fan.send_ir("fan_off.ir")
    mock_subprocess_run.assert_called_once_with(
        ["ir-ctl", "-s", str(config.IR_DIR / "fan_off.ir")],
        check=True,
        timeout=5,
    )


def test_send_ir_with_device(mock_subprocess_run):
    fan.send_ir("fan_off.ir", ir_device="/dev/lirc1")
    mock_subprocess_run.assert_called_once_with(
        ["ir-ctl", "-d", "/dev/lirc1", "-s", str(config.IR_DIR / "fan_off.ir")],
        check=True,
        timeout=5,
    )


def test_send_ir_uses_config_ir_device(mock_subprocess_run, monkeypatch):
    monkeypatch.setattr(config, "IR_DEVICE", "/dev/lirc2")
    fan.send_ir("fan_off.ir")
    mock_subprocess_run.assert_called_once_with(
        ["ir-ctl", "-d", "/dev/lirc2", "-s", str(config.IR_DIR / "fan_off.ir")],
        check=True,
        timeout=5,
    )
