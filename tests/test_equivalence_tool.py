import pytest

from tools.verify_modsim_equivalence import same_value


@pytest.mark.parametrize(
    "left, right",
    [
        (12.34, 12.34000015258789),
        ("-12.34", "-12.34000015258789"),
        (1, 1.0),
        ("text", "text"),
    ],
)
def test_one_reading_in_two_precisions_is_the_same_value(left, right):
    assert same_value(left, right)


@pytest.mark.parametrize(
    "left, right",
    [
        (12.34, 12.35),
        (12.34, 12.340001),
        (True, 1),
        ("12.34", "text"),
        (1.0, float("nan")),
    ],
)
def test_different_readings_are_not_the_same_value(left, right):
    assert not same_value(left, right)


def test_snapshots_compare_every_point_of_every_device():
    from tools.verify_modsim_equivalence import snapshots_match

    base = {"meter": {"value": 12.34, "name": "a"}}
    assert snapshots_match(base, {"meter": {"value": 12.34000015258789, "name": "a"}})
    assert not snapshots_match(base, {"meter": {"value": 12.35, "name": "a"}})
    assert not snapshots_match(base, {"meter": {"value": 12.34}})
