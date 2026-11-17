# tests/test_encode_inverse.py
import os

from ftm150 import CloneImage
from tests.files import ALL_A, ALL_B, load

PATHS = [ALL_A, ALL_B]

# fields that are fully decoded AND have setters (the lossless set)
FIELDS = ["band", "rx_hz", "mode", "narrow", "shift", "tone_mode", "step_khz",
          "power", "ctcss_hz", "dcs", "skip", "mgrp", "clock_shift",
          "user_ctcss_hz", "offset_hz", "name"]


def test_split_tx_hz_is_inverse():
    """For split-shift channels, round-tripping tx_hz leaves bytes unchanged."""
    found = False
    for path in PATHS:
        img = load(CloneImage, path)
        for ch in img.memory.channels:
            if ch.enabled and ch.shift == "split":
                before = ch.raw
                ch.tx_hz = ch.tx_hz
                assert ch.raw == before, f"{os.path.basename(path)} split tx churn"
                found = True
    assert found, "expected at least one split channel in the fixtures"


def test_assigning_decoded_value_leaves_bytes_unchanged():
    """For every populated regular channel, round-tripping each field via its
    setter (set to its own current value) must not change any byte."""
    for path in PATHS:
        img = load(CloneImage, path)
        for ch in img.memory.channels:
            if not ch.enabled:
                continue
            before = ch.raw
            for f in FIELDS:
                setattr(ch, f, getattr(ch, f))
            assert ch.raw == before, f"{os.path.basename(path)} '{ch.name}' field churn"


def test_frequency_edge_text_is_exact_inverse():
    """Every decoded frequency is int Hz and survives the CSV MHz text exactly."""
    from ftm150 import units
    for path in PATHS:
        img = load(CloneImage, path)
        for ch in img.memory.channels:
            if not ch.enabled:
                continue
            for hz in (ch.rx_hz, ch.tx_hz):
                assert type(hz) is int
                assert units.mhz_to_hz(units.hz_to_mhz_text(hz)) == hz
            assert units.mhz_to_hz(units.hz_to_mhz_fixed3(ch.offset_hz)) == ch.offset_hz
