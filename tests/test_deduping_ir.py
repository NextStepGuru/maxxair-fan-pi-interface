from maxxair_fan.backends.deduping_ir import DedupingIRBackend
from maxxair_fan.backends.fake_ir import FakeIRBackend


def test_deduping_ir_resets():
    dedupe = DedupingIRBackend(FakeIRBackend())
    dedupe.send("fan_off.ir")
    dedupe.reset()
    assert dedupe.last_sent is None
