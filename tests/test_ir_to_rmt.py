import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "ir_to_rmt.py"
IR_DIR = REPO_ROOT / "ir_codes"
GENERATED_HEADER = REPO_ROOT / "firmware" / "atoms3-agent" / "src" / "ir_timings.h"


def load_ir_to_rmt():
    spec = importlib.util.spec_from_file_location("ir_to_rmt", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ir_to_rmt = load_ir_to_rmt()


def test_parse_fan_off_starts_with_pulse_and_skips_timeout():
    signal = ir_to_rmt.parse_ir_file(IR_DIR / "fan_off.ir")
    assert signal.filename == "fan_off.ir"
    assert signal.carrier_hz == 40000
    assert signal.timings[0] == 1670
    assert signal.timings[1] == 816
    assert 129163 not in signal.timings


def test_all_ir_files_parse_and_share_40khz_carrier():
    signals = ir_to_rmt.load_ir_dir(IR_DIR)
    names = {signal.filename for signal in signals}
    assert "fan_off.ir" in names
    assert "fan_on_in_10.ir" in names
    assert "fan_on_out_100.ir" in names
    assert len(signals) == 21
    assert {signal.carrier_hz for signal in signals} == {40000}
    assert all(signal.timings for signal in signals)


def test_c_identifier():
    assert ir_to_rmt.c_identifier("fan_on_in_40.ir") == "IR_fan_on_in_40"
    assert ir_to_rmt.c_identifier("10-off.ir") == "IR__10_off"


def test_parse_rejects_pulse_space_mismatch(tmp_path: Path):
    path = tmp_path / "bad.ir"
    path.write_text("carrier 40000\npulse 100\npulse 200\n")
    with pytest.raises(ValueError, match="expected space"):
        ir_to_rmt.parse_ir_file(path)


def test_generated_header_is_current():
    signals = ir_to_rmt.load_ir_dir(IR_DIR)
    expected = ir_to_rmt.render_header(signals)
    assert GENERATED_HEADER.read_text() == expected
    assert "fan_off.ir" in expected
    assert "IR_CARRIER_KHZ = 40" in expected
    assert "IR_CODE_COUNT = 21" in expected
