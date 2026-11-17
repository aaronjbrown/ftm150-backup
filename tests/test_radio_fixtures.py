"""Pin the radio-made fixture images: a fictional configuration, backed up by the radio.

ALL_A is the first ALL backup; ALL_B is the same configuration after a few front-panel
edits (name display on CH4-8, APO 2.0 h, VFO B 145.200 MHz). MEMORY_B and SETUP_B were
taken back to back with ALL_B.
"""
import pytest

from ftm150.engine.image import CloneImage
from ftm150.engine.tables import Band
from tests.files import ALL_A, ALL_B, MEMORY_B, SETUP_B, load, read

NAMES = {1: "RPT2M-A", 2: "RPT2M-B", 3: "RPT70-A", 4: "RPT70-B", 5: "SIMPLEX", 6: "DCS-CH",
         7: "SPLIT", 8: "NARROW", 9: "AIR-EMRG", 10: "222-BAND", 11: "SKIPGRP",
         12: "CLKSHIFT", 13: "STEP6.25", 14: "STEP10", 15: "STEP15", 16: "STEP20",
         17: "STEP50", 18: "STEP100", 20: "CB CH1", 21: "CB CH2"}

# ch: (band, rx_hz, shift, offset_hz, tx_hz, tone_mode, tone, mode, power, step_code,
#      narrow, skip, mgrp, clock_shift, user_ctcss_hz).  tone is the CTCSS Hz for
# TONE/TSQL, the DCS code for DCS, None for OFF (OFF keeps stale tone values stored).
V, U, A, X = Band.VHF, Band.UHF, Band.AIR, Band.VHF_UHF
ROWS = {
    1: (V, 146_900_000, "-RPT", 600_000, None, "TONE", 123.0, "FM", "MED", 0, 0, 0, 0, 0, 1500),
    2: (V, 147_250_000, "+RPT", 600_000, None, "TSQL", 91.5, "FM", "HIGH", 0, 0, 0, 0, 0, 1500),
    3: (U, 438_150_000, "-RPT", 5_000_000, None, "TONE", 91.5, "FM", "HIGH", 7, 0, 0, 0, 0, 1500),
    4: (U, 438_500_000, "-RPT", 7_000_000, None, "TONE", 100.0, "FM", "LOW", 7, 0, 0, 0, 0, 1500),
    5: (V, 146_500_000, "simplex", 0, None, "OFF", None, "FM", "HIGH", 0, 0, 0, 0, 0, 1500),
    6: (U, 439_125_000, "simplex", 0, None, "DCS", 205, "FM", "HIGH", 7, 0, 0, 0, 0, 1500),
    7: (V, 146_000_000, "split", 0, 147_000_000, "OFF", None, "FM", "HIGH", 0, 0, 0, 0, 0, 1500),
    8: (U, 439_000_000, "simplex", 0, None, "OFF", None, "FM", "LOW", 4, 1, 0, 0, 0, 1500),
    9: (A, 121_500_000, "simplex", 0, None, "OFF", None, "AM", "HIGH", 7, 0, 0, 0, 0, 1500),
    10: (X, 223_500_000, "simplex", 0, None, "OFF", None, "FM", "HIGH", 4, 0, 0, 0, 0, 1500),
    11: (V, 145_000_000, "simplex", 600_000, None, "OFF", None, "FM", "HIGH", 0, 0, 1, 1, 0, 1500),
    12: (V, 145_500_000, "simplex", 600_000, None, "OFF", None, "FM", "HIGH", 0, 0, 0, 0, 1, 1000),
    13: (V, 145_250_000, "simplex", 0, None, "OFF", None, "FM", "HIGH", 1, 0, 0, 0, 0, 1500),
    14: (V, 145_260_000, "simplex", 0, None, "OFF", None, "FM", "HIGH", 3, 0, 0, 0, 0, 1500),
    15: (V, 145_275_000, "simplex", 0, None, "OFF", None, "FM", "HIGH", 5, 0, 0, 0, 0, 1500),
    16: (V, 145_280_000, "simplex", 0, None, "OFF", None, "FM", "HIGH", 6, 0, 0, 0, 0, 1500),
    17: (V, 145_350_000, "simplex", 0, None, "OFF", None, "FM", "HIGH", 8, 0, 0, 0, 0, 1500),
    18: (V, 145_400_000, "simplex", 0, None, "OFF", None, "FM", "HIGH", 9, 0, 0, 0, 0, 1500),
    20: (U, 476_425_000, "simplex", 0, None, "OFF", None, "FM", "HIGH", 4, 0, 0, 0, 0, 1500),
    21: (U, 476_450_000, "simplex", 0, None, "OFF", None, "FM", "HIGH", 4, 0, 0, 0, 0, 1500),
}


@pytest.mark.parametrize("path", [ALL_A, ALL_B])
def test_only_the_documented_names_exist(path):
    img = load(CloneImage, path)
    assert {n: c.name for n, c in img.memory.channels.items() if c.name} == NAMES


@pytest.mark.parametrize("path", [ALL_A, ALL_B])
def test_label_regions_hold_no_text(path):
    data = read(path)
    for lo, hi in ((0x3B0, 0x3E8), (0x480, 0x498)):
        assert set(data[lo:hi]) == {0xFF}


@pytest.mark.parametrize("path", [ALL_A, ALL_B])
@pytest.mark.parametrize("n", sorted(ROWS))
def test_channel_row(path, n):
    (band, rx, shift, offset, tx, tone_mode, tone, mode, power, step_code, narrow, skip, mgrp,
     clock_shift, user_ctcss) = ROWS[n]
    ch = load(CloneImage, path).memory.channels[n]
    assert ch.enabled is True
    assert ch.band == band
    assert ch.rx_hz == rx
    assert ch.shift == shift
    assert ch.offset_hz == offset
    if tx is not None:
        assert ch.tx_hz == tx
    elif shift == "simplex":
        assert ch.tx_hz == rx
    assert ch.tone_mode == tone_mode
    if tone_mode in ("TONE", "TSQL"):
        assert ch.ctcss_hz == tone
    elif tone_mode == "DCS":
        assert ch.dcs == tone
    assert ch.mode == mode
    assert ch.power == power
    assert ch.raw[5] & 0x0F == step_code
    assert (ch.narrow, ch.skip, ch.mgrp, ch.clock_shift) == (
        bool(narrow), bool(skip), bool(mgrp), bool(clock_shift))
    assert ch.user_ctcss_hz == user_ctcss


@pytest.mark.parametrize("path", [ALL_A, ALL_B])
@pytest.mark.parametrize("n", [200, 500, 999])
def test_empty_slots(path, n):
    assert load(CloneImage, path).memory.channels[n].enabled is False


@pytest.mark.parametrize("path", [ALL_A, ALL_B])
def test_home_vfo_and_pms(path):
    img = load(CloneImage, path)
    assert img.memory.pms[1].lower.rx_hz == 144_100_000
    assert img.memory.pms[1].upper.rx_hz == 145_900_000
    assert img.memory.home_a[Band.VHF].rx_hz == 145_300_000
    assert img.memory.home_b[Band.VHF].rx_hz == 145_400_000
    assert img.setup.vfo_a[Band.VHF].rx_hz == 145_300_000


@pytest.mark.parametrize("path", [ALL_A, ALL_B])
def test_scan_resume(path):
    s = load(CloneImage, path).setup.settings
    assert (s.scan_resume_a, s.scan_resume_b) == ("5SEC", "3SEC")


def test_b_is_a_with_the_edits():
    a, b = load(CloneImage, ALL_A), load(CloneImage, ALL_B)
    for n in range(4, 9):
        assert a.memory.channels[n].show_name is False
        assert b.memory.channels[n].show_name is True
    assert a.setup.settings.apo == "1.0h"
    assert b.setup.settings.apo == "2.0h"
    assert b.setup.vfo_b[Band.VHF].rx_hz == 145_200_000


def test_name_display_flags():
    for path, shown in ((ALL_A, {20, 21}), (ALL_B, {4, 5, 6, 7, 8, 20, 21})):
        mem = load(CloneImage, path).memory
        assert {n for n, c in mem.channels.items() if c.enabled and c.show_name} == shown


def test_partials_match_the_all_backup_taken_with_them():
    b = load(CloneImage, ALL_B)
    assert read(MEMORY_B) == b.memory.to_bytes()
    assert read(SETUP_B) == b.setup.to_bytes()


@pytest.mark.parametrize("path", [ALL_A, ALL_B, MEMORY_B, SETUP_B])
def test_header_checksum(path):
    data = read(path)
    assert sum(data[:0x7F]) & 0xFF == data[0x7F]
    assert data[8:11] == b"\x01\x01\x01"
