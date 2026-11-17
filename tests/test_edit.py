# tests/test_edit.py

import pytest

from ftm150 import CloneImage
from tests.files import ALL_A, load


def _ch1(path=ALL_A):
    return load(CloneImage, path).memory.channels[1]


def test_set_frequency_reads_back_and_is_local():
    img = load(CloneImage, ALL_A)
    ch = img.memory.channels[1]
    before = bytearray(ch.raw)
    ch.rx_hz = 147_375_000        # a +5 kHz freq
    assert ch.rx_hz == 147_375_000
    after = ch.raw
    # only rec[2..4] changed
    changed = [i for i in range(16) if before[i] != after[i]]
    assert changed and all(i in (2, 3, 4) for i in changed)


def test_setting_ctcss_out_of_table_raises():
    ch = _ch1()
    with pytest.raises(ValueError):
        ch.ctcss_hz = 99.9        # not a real CTCSS tone


def test_invalid_setter_does_not_mutate_buffer():
    ch = _ch1()
    before = bytes(ch.raw)
    with pytest.raises(ValueError):
        ch.rx_hz = 999_000_000    # outside all bands
    assert ch.raw == before
