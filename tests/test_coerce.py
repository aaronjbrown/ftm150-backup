import pytest

from ftm150 import coerce, units
from ftm150.engine.tables import Band, RawCode


def _v(field, value):
    """coerce() returns (engine field, value); for non-aliased fields the
    engine field is the field itself."""
    engine_field, v = coerce.coerce(field, value)
    assert engine_field == field
    return v


def test_coerce_band_by_name():
    assert _v("band", "VHF") is Band.VHF


def test_coerce_bool():
    assert _v("skip", "yes") is True


def test_coerce_unknown_field_raises():
    with pytest.raises(KeyError):
        coerce.coerce("bogus", "1")


def test_coerce_only_parses():
    assert _v("shift", "minus") == "minus"
    assert _v("power", "3") == 3
    assert isinstance(_v("power", "3"), RawCode)
    assert _v("shift", "5") == 5
    with pytest.raises(ValueError):
        _v("step_khz", "AUTO")
    assert _v("step_khz", "6.25") == 6.25
    assert _v("step_khz", "7") == 7.0
    assert isinstance(_v("step_khz", "7"), float)


def test_settable_field_set_unchanged():
    # Exactly the 19 user-facing names; the engine's int-Hz names stay internal.
    assert set(coerce.SETTABLE) == {
        "name", "band", "rx_mhz", "tx_mhz", "mode", "narrow", "shift",
        "tone_mode", "step_khz", "power", "ctcss_hz", "dcs", "skip", "mgrp",
        "clock_shift", "user_ctcss_hz", "offset_khz", "enabled", "show_name"}
    assert {
        "rx_mhz": ("rx_hz", units.mhz_to_hz),
        "tx_mhz": ("tx_hz", units.mhz_to_hz),
        "offset_khz": ("offset_hz", units.khz_to_hz)} == coerce.EDGE_ALIASES


@pytest.mark.parametrize("text", ["146.65", "146.6500", " 146.65 ", "146.650000"])
def test_coerce_mhz_alias_is_exact(text):
    assert coerce.coerce("rx_mhz", text) == ("rx_hz", 146_650_000)
    assert coerce.coerce("tx_mhz", text) == ("tx_hz", 146_650_000)


@pytest.mark.parametrize("field", ["rx_hz", "tx_hz", "offset_hz"])
def test_engine_hz_names_not_settable(field):
    with pytest.raises(KeyError) as e:
        coerce.coerce(field, "146650000")
    listed = set(str(e.value).split("settable: ")[1].rstrip("\"'").split(", "))
    assert listed == set(coerce.SETTABLE)
    assert not listed & {"rx_hz", "tx_hz", "offset_hz"}


def test_coerce_khz_alias_is_exact():
    assert coerce.coerce("offset_khz", "600") == ("offset_hz", 600_000)


@pytest.mark.parametrize("text", ["abc", "", "146.6500001"])
def test_coerce_mhz_alias_rejects(text):
    with pytest.raises(ValueError):
        coerce.coerce("rx_mhz", text)


def test_display_is_in_the_users_units():
    assert coerce.display("rx_mhz", 146_520_000) == "146.52"
    assert coerce.display("tx_mhz", 147_000_000) == "147.0"   # str(float)
    assert coerce.display("offset_khz", 600_000) == "600"
    assert coerce.display("ctcss_hz", 88.5) == "88.5"
