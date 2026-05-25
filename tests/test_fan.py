from maxxair_fan import config, fan
from maxxair_fan.backends.deduping_ir import DedupingIRBackend
from maxxair_fan.backends.fake_ir import FakeIRBackend


def test_resolve_ir_filename_off():
    assert fan.resolve_ir_filename("in", 0) == "fan_off.ir"
    assert fan.resolve_ir_filename("out", 0) == "fan_off.ir"


def test_resolve_ir_filename_in_and_out():
    assert fan.resolve_ir_filename("in", 50) == "fan_on_in_50.ir"
    assert fan.resolve_ir_filename("out", 50) == "fan_on_out_50.ir"


def test_send_ir_returns_true_on_success(mocker):
    mocker.patch("maxxair_fan.fan.subprocess.run", return_value=mocker.Mock(returncode=0))
    assert fan.send_ir("fan_off.ir") is True


def test_send_ir_returns_false_on_failure(mocker):
    mocker.patch("maxxair_fan.fan.subprocess.run", side_effect=OSError("fail"))
    assert fan.send_ir("fan_off.ir") is False


def test_send_ir_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "IR_DIR", tmp_path)
    assert fan.send_ir("fan_off.ir") is False


def test_deduping_ir_backend():
    inner = FakeIRBackend()
    dedupe = DedupingIRBackend(inner)

    assert dedupe.send("fan_on_in_50.ir") is True
    assert dedupe.send("fan_on_in_50.ir") is True
    assert inner.sent == ["fan_on_in_50.ir"]
    assert dedupe.last_sent == "fan_on_in_50.ir"


def test_deduping_ir_send_failure_does_not_update_last(mocker):
    inner = FakeIRBackend()
    dedupe = DedupingIRBackend(inner)
    mocker.patch.object(inner, "send", return_value=False)

    assert dedupe.send("fan_on_in_50.ir") is False
    assert dedupe.last_sent is None
