# tests/test_units.py — exact decimal MHz/kHz <-> integer Hz at the edges.
import time

import pytest

from ftm150 import units
from ftm150.engine.tables import Band


@pytest.mark.parametrize("text", ["146.65", "146.6500", " 146.65 ", "146.650000", 146.65])
def test_mhz_text_variants(text):
    assert units.mhz_to_hz(text) == 146_650_000


@pytest.mark.parametrize("bad", ["abc", "", "146.6500001",
                                 "146.6500000000000000000000000001",  # > 28 digits
                                 "NaN", "Infinity", "1e999999999"])
def test_mhz_rejects(bad):
    with pytest.raises(ValueError):
        units.mhz_to_hz(bad)


def test_off_grid_refused_by_engine(blank):
    _, ch = blank
    with pytest.raises(ValueError, match=r"2\.5 kHz"):
        ch.retune(Band.VHF, units.mhz_to_hz("146.65125"))


def test_text_formatting_matches_csv_columns():
    assert units.hz_to_mhz_text(146_650_000) == "146.65"
    assert units.hz_to_mhz_text(438_025_000) == "438.025"
    assert units.hz_to_mhz_fixed3(600_000) == "0.600"


@pytest.mark.parametrize("bad", ["0e999999999", "0e-999999999", "1e-999999999",
                                 "-0e999999999", "1" * 1000, "0." + "0" * 1000])
def test_mhz_absurd_input_refused_cheaply(bad):
    # DoS guard: an exponent or digit count no frequency needs is refused before
    # any 10**n is built -- zeros included (no value-dependent bypass).
    t = time.perf_counter()
    with pytest.raises(ValueError, match="out of range"):
        units.mhz_to_hz(bad)
    with pytest.raises(ValueError, match="out of range"):
        units.khz_to_hz(bad)
    assert time.perf_counter() - t < 0.1


@pytest.mark.parametrize("zero", ["0", "-0", "0.000", "0e-9", "-0.0"])
def test_mhz_zero_forms(zero):
    assert units.mhz_to_hz(zero) == 0
