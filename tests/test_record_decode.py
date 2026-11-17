# tests/test_record_decode.py

from ftm150 import Band, Channel, CloneImage, layout
from tests.files import ALL_A, load


def _chan(path, n):
    img = load(CloneImage, path)
    off = layout.CH_BASE + (n - 1) * layout.CH_STRIDE
    name = layout.NAME_BASE + (n - 1) * layout.CH_STRIDE
    return Channel(img._buf, off, name)


def test_regular_channel():
    ch = _chan(ALL_A, 1)
    assert ch.enabled is True
    assert ch.name == "RPT2M-A"
    assert ch.band == Band.VHF
    assert ch.rx_hz == 146_900_000
    assert ch.mode == "FM"
    assert ch.shift == "-RPT"
    assert ch.offset_hz == 600_000
    assert ch.tx_hz == 146_300_000
    assert ch.tone_mode == "TONE"
    assert ch.ctcss_hz == 123.0
    assert ch.power == "MED"


def test_cb_ch1_uhf_with_5khz_flag():
    # CH20 = 'CB CH1' = 476.4250 (needs +5 kHz flag)
    ch = _chan(ALL_A, 20)
    assert ch.name == "CB CH1"
    assert ch.band == Band.UHF
    assert ch.rx_hz == 476_425_000
    assert ch.step_khz == 12.5


def test_empty_channel_disabled():
    ch = _chan(ALL_A, 500)
    assert ch.enabled is False
