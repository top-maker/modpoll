"""scaled_raw inverts the engineering value modpoll computes (WOT-05)."""

from fractions import Fraction

from hypothesis import given, strategies as st
import pytest

from modpoll_wot import DataError, scaled_raw

# Multipliers as written in Thing Models: decimal strings, including negative and integer ones.
MULTIPLIERS = st.sampled_from(
    ["0.1", "0.01", "0.001", "0.0001", "0.5", "0.25", "10", "1000", "-0.1", "-2", "1"]
)
# Register-sized raw integers up to 32 bits; wider values carry no float multiplier.
RAWS = st.integers(min_value=-(2**31), max_value=2**32 - 1)


@given(raw=RAWS, multiplier=MULTIPLIERS)
def test_the_float_modpoll_computes_maps_back_to_its_raw_value(raw, multiplier):
    assert scaled_raw(float(raw) * float(Fraction(multiplier)), multiplier) == raw


@given(raw=RAWS, multiplier=MULTIPLIERS)
def test_the_exact_decimal_value_maps_back_to_its_raw_value(raw, multiplier):
    exact = Fraction(raw) * Fraction(multiplier)
    if exact.denominator == 1:
        assert scaled_raw(int(exact), multiplier) == raw


@given(raw=st.integers(min_value=-(2**20), max_value=2**20), multiplier=MULTIPLIERS)
def test_a_value_halfway_between_two_raw_values_is_refused(raw, multiplier):
    halfway = (Fraction(raw) + Fraction(1, 2)) * Fraction(multiplier)
    with pytest.raises(DataError):
        scaled_raw(float(halfway), multiplier)
