from ftm150 import layout, tables
from ftm150.engine.partial import LAYOUTS, Kind


def test_ctcss_table_indices():
    assert len(tables.CTCSS_TABLE) == 50
    assert tables.CTCSS_TABLE[9] == 91.5
    assert tables.CTCSS_TABLE[12] == 100.0


def test_dcs_table_indices():
    assert tables.DCS_TABLE[0] == 23
    assert tables.DCS_TABLE[33] == 205


def test_band_ranges():
    assert tables.Band.VHF == 1
    lo, hi = tables.BAND_RANGES[tables.Band.UHF]
    assert (lo, hi) == (400_000_000, 550_000_000)


def test_layout_constants():
    assert LAYOUTS[Kind.ALL].size == 0x18000
    assert layout.MAGIC == b"AH086$"
    assert layout.CH_BASE == 0x800
    assert layout.NUM_REGULAR == 999
    assert layout.NAME_BASE == 0x10000
    assert layout.PMS_BASE == 0x4670
    assert layout.VFO_A_BASE == 0x100
    assert layout.HOME_B_BASE == 0x1f0
