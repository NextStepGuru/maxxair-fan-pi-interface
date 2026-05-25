import pytest

from maxxair_fan.fan import compute_speed


@pytest.mark.parametrize(
    "current, target, expected",
    [
        (72.0, 72.0, 0),
        (71.0, 72.0, 0),
        (72.5, 72.0, 10),
        (73.0, 72.0, 20),
        (73.5, 72.0, 40),
        (74.0, 72.0, 80),
        (74.5, 72.0, 100),
        (80.0, 72.0, 100),
    ],
)
def test_compute_speed_matt_curve(current, target, expected):
    assert compute_speed(current, target) == expected


def test_compute_speed_at_exactly_zero_diff():
    assert compute_speed(72.0, 72.0) == 0


def test_compute_speed_large_diff_caps_at_100():
    assert compute_speed(100.0, 72.0) == 100


def test_compute_speed_rounds_to_nearest_ten():
    # Between 73.0 (+20) and 73.5 (+40), intermediate values round
    assert compute_speed(73.25, 72.0) in (20, 30, 40)


def test_compute_speed_custom_gradient_and_exponent():
    speed = compute_speed(73.0, 72.0, gradient_degrees=1.0, exponent_value=2.0)
    assert speed == 10
