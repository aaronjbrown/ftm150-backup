# encode_freq must refuse what the confirmed format cannot hold (2.5 kHz grid),
# never silently floor it to a different frequency.
import dataclasses
import re

import pytest

from ftm150 import CloneImage, coerce
from ftm150.coerce import parse_band
from ftm150.engine import layout, record
from ftm150.engine.fields import _Field, decode_freq, encode_freq
from ftm150.engine.record import Channel, write_record
from ftm150.engine.tables import BAND_RANGES, Band, RawCode
from tests.files import ALL_A, ALL_B, load

CH1_REC = 0x800  # CH1's 16-byte record in a synthetic image


@pytest.mark.parametrize("hz", [146_700_500, 146_706_250, 146_701_250, 438_000_100])
def test_encode_freq_refuses_off_grid(hz):
    with pytest.raises(ValueError, match=r"2\.5 kHz"):
        encode_freq(hz)


@pytest.mark.parametrize("hz", [146_700_000, 146_705_000, 438_275_000, 108_000_000,
                                549_995_000, 476_437_500, 549_997_500])
def test_encode_freq_on_grid_roundtrips(hz):
    assert decode_freq(*encode_freq(hz)) == hz


@pytest.mark.parametrize("hz", [1_000_000_000, -5_000])
def test_encode_freq_refuses_out_of_bcd_range(hz):
    # 5 BCD digits of 10 kHz: never wrap 1000 MHz to 0 MHz.
    with pytest.raises(ValueError, match="BCD"):
        encode_freq(hz)


def test_encode_freq_refuses_float_mhz():
    with pytest.raises(TypeError):
        encode_freq(146.7)  # type: ignore[arg-type]


def test_mhz_names_are_not_engine_attributes(blank):
    _, ch = blank
    for name in ("rx_mhz", "tx_mhz", "offset_khz"):
        with pytest.raises(AttributeError):
            setattr(ch, name, 1)


# --- name-present flag: 2 bytes/channel @ 0x4CB0 + (n-1)*2 ------------------
# ADMS-17 shows names as boxes without this word; in both fixture
# backups this word is 00 00 exactly when the channel has a name tag.
_BACKUPS = [ALL_A, ALL_B]


def _flag(img, n):
    o = layout.NAME_FLAG_BASE + (n - 1) * layout.NAME_FLAG_STRIDE
    return bytes(img._buf[o:o + 2])


@pytest.mark.parametrize("path", _BACKUPS)
def test_real_backups_name_flag_iff_named(path):
    img = load(CloneImage, path)
    for n in range(1, layout.NUM_REGULAR + 1):
        named = img.memory.channels[n].name != ""
        assert _flag(img, n) == (b"\x00\x00" if named else b"\xff\xff"), n


def test_setting_name_sets_flag_and_clearing_resets_it():
    img = load(CloneImage, ALL_B)
    n = 500
    assert img.memory.channels[n].name == "" and _flag(img, n) == b"\xff\xff"
    img.memory.channels[n].name = "N0NAME"
    assert _flag(img, n) == b"\x00\x00"
    img.memory.channels[n].name = ""
    assert _flag(img, n) == b"\xff\xff"


def test_renaming_existing_named_channel_keeps_bytes_consistent():
    img = load(CloneImage, ALL_B)
    before = bytes(img._buf)
    img.memory.channels[4].name = img.memory.channels[4].name   # no-op rename
    assert bytes(img._buf) == before


# --- rec[11]: bit 7 = display name (1) vs frequency (0); bits 6-0 = user CTCSS/100 ---
# Within the channel records, ALL_B differs from ALL_A only in CH4-8 being switched to
# name display on the radio; that flipped ONLY rec[11] bit 7 (0x0f -> 0x8f) on each.
# (ALL_B also differs in SETUP bytes, outside the channel records.)


def test_display_flip_is_only_rec11_bit7():
    a, b = load(CloneImage, ALL_A), load(CloneImage, ALL_B)
    lo = layout.CH_BASE
    hi = lo + layout.NUM_REGULAR * layout.CH_STRIDE
    assert hi == 0x4670
    diffs = {i: a._buf[i] ^ b._buf[i] for i in range(lo, hi) if a._buf[i] != b._buf[i]}
    assert diffs == {lo + (n - 1) * layout.CH_STRIDE + 11: 0x80 for n in (4, 5, 6, 7, 8)}
    for n in (4, 5, 6, 7, 8):
        assert not a.memory.channels[n].show_name and b.memory.channels[n].show_name


def test_name_flag_tracks_name_not_enabled(blank):
    img, _ = blank
    ch = img.memory.channels
    ch[10].retune(Band.VHF, 146_000_000)
    ch[10].enabled = True
    ch[10].name = ""
    assert ch[10].enabled and _flag(img, 10) == b"\xff\xff"      # enabled, no name
    ch[11].retune(Band.VHF, 146_000_000)
    ch[11].enabled = True
    ch[11].name = "NAMED"
    ch[11].enabled = False
    assert not ch[11].enabled and _flag(img, 11) == b"\x00\x00"  # disabled, named


def test_user_ctcss_ignores_display_bit():
    img = load(CloneImage, ALL_B)
    assert img._buf[0x800 + 3 * 16 + 11] == 0x8f       # CH4: name display, 1500 Hz
    assert img.memory.channels[4].user_ctcss_hz == 1500
    assert img.memory.channels[4].show_name is True


def test_user_ctcss_setter_preserves_display_bit():
    img = load(CloneImage, ALL_B)
    img.memory.channels[4].user_ctcss_hz = 1000
    assert img.memory.channels[4].show_name is True
    assert img.memory.channels[4].user_ctcss_hz == 1000


def test_show_name_setter_touches_only_bit7():
    img = load(CloneImage, ALL_B)
    before = bytes(img._buf)
    img.memory.channels[4].show_name = False
    after = bytes(img._buf)
    diffs = [i for i in range(len(before)) if before[i] != after[i]]
    assert diffs == [0x800 + 3 * 16 + 11] and after[diffs[0]] == 0x0f


def test_user_ctcss_carries_undecoded_bits_5_6(blank):
    # the firmware masks rec[11] with 0x1F; bits 5-6 are undecoded, kept verbatim
    img, ch = blank
    img._buf[0x80B] = 0x60 | 15
    assert ch.user_ctcss_hz == 1500
    ch.user_ctcss_hz = 1000
    assert img._buf[0x80B] == 0x60 | 10


@pytest.mark.parametrize("hz", [200, 3100, 1550, 14300])
def test_user_ctcss_setter_refuses_out_of_range(hz):
    img = load(CloneImage, ALL_B)
    with pytest.raises(ValueError):
        img.memory.channels[4].user_ctcss_hz = hz


def test_unknown_codes_read_as_raw_ints(blank):
    img, ch = blank
    img._buf[0x801] = 0x05
    img._buf[0x809] = 0xC0
    img._buf[0x805] = 0x3C
    img._buf[0x800] = 0x06
    assert (ch.shift, ch.power, ch.tone_mode, ch.step_khz, ch.band) == (5, 3, 3, 12, 6)


def test_raw_codes_write_back_unchanged(blank):
    img, ch = blank
    ch.shift = RawCode(5)
    ch.power = RawCode(3)
    assert img._buf[0x801] & 0x07 == 5 and img._buf[0x809] >> 6 == 3


@pytest.mark.parametrize("field,value,expect", [
    ("shift", "minus", "simplex, -RPT, +RPT, split"),
    ("power", "MAX", "HIGH, MED, LOW"),
    ("step_khz", 7.0, "5.0, 6.25, 10.0"),
    ("band", 1, "band: 1 not one of"),
    ("power", 3, "HIGH, MED, LOW"),
    ("shift", RawCode(8), "shift: RawCode(8) out of range 0..7"),
    ("power", RawCode(4), "power: RawCode(4) out of range 0..3"),
    ("shift", True, "shift: True not one of"),
])
def test_bad_choice_lists_valid(blank, field, value, expect):
    _, ch = blank
    with pytest.raises(ValueError, match=re.escape(expect)):
        setattr(ch, field, value)


def test_band_enum_and_raw_int(blank):
    _, ch = blank
    ch.band = Band.VHF
    assert ch.band is Band.VHF
    ch.band = RawCode(6)
    assert ch.band == 6 and not isinstance(ch.band, Band)


@pytest.mark.parametrize("name,band", [("VHF", Band.VHF), ("uhf", Band.UHF),
                                       (" Vhf_Uhf ", Band.VHF_UHF), ("air", Band.AIR)])
def test_band_accepts_name_label(blank, name, band):
    _, ch = blank
    ch.band = name
    assert ch.band is band
    ch.retune(name, BAND_RANGES[band][0])
    assert ch.band is band


@pytest.mark.parametrize("name", ["HF", "", "1", "VHF UHF"])
def test_band_rejects_unknown_name(blank, name):
    _, ch = blank
    with pytest.raises(ValueError, match=r"band: .* not one of AIR, VHF, VHF_UHF, UHF"):
        ch.band = name


def test_band_name_is_range_checked_on_enabled_record(blank):
    _, ch = blank
    ch.enabled = True
    ch.retune(Band.VHF, 146_500_000)
    with pytest.raises(ValueError, match="outside band"):
        ch.band = "uhf"


@pytest.mark.parametrize("code", [1, 5, 6, 7])
def test_tx_hz_refuses_undecoded_shift(blank, code):
    """Never guess: an undecoded shift has no known tx (was silently rx)."""
    _, ch = blank
    ch.retune(Band.VHF, 146_500_000)
    ch.shift = RawCode(code)
    with pytest.raises(ValueError,
                       match=re.escape(f"tx frequency unknown: shift code {code} is undecoded")):
        _ = ch.tx_hz
    assert ch.to_record().tx_hz is None          # snapshots never read tx for non-split


def test_unknown_codes_are_rawcode_type(blank):
    img, ch = blank
    img._buf[0x801] = 0x05
    assert isinstance(ch.shift, RawCode) and repr(ch.shift) == "RawCode(5)"


@pytest.mark.parametrize("code,khz", [(0, 5.0), (1, 6.25), (3, 10.0), (4, 12.5), (5, 15.0),
                                      (6, 20.0), (7, 25.0), (8, 50.0), (9, 100.0)])
def test_step_codes(blank, code, khz):
    img, ch = blank
    img._buf[0x805] = (img._buf[0x805] & 0xF0) | code
    assert ch.step_khz == khz
    ch.step_khz = khz
    assert img._buf[0x805] & 0x0F == code


def test_step_code_2_stays_raw(blank):
    img, ch = blank
    img._buf[0x805] = (img._buf[0x805] & 0xF0) | 2
    assert isinstance(ch.step_khz, RawCode) and ch.step_khz == 2


def test_auto_step_refused(blank):
    _, ch = blank
    with pytest.raises(ValueError):
        ch.step_khz = "AUTO"


def test_step_plain_int_is_a_label(blank):
    _, ch = blank
    ch.step_khz = 25
    assert ch.step_khz == 25.0


def test_raw_band_rx_setter_skips_range_but_keeps_grid(blank):
    _, ch = blank
    ch.band = RawCode(6)
    ch.rx_hz = 146_500_000
    assert ch.rx_hz == 146_500_000
    with pytest.raises(ValueError, match="5 kHz"):
        ch.rx_hz = 146_500_100


def test_offset_refuses_unconfirmed_high_byte(blank):
    # rec[12] is probably the offset's high byte (spec §7); until a capture
    # confirms it, a non-zero value is refused rather than misread
    img, ch = blank
    img._buf[0x80C:0x80E] = bytes([0x01, 0x90])         # 20 MHz if u16
    with pytest.raises(ValueError, match="offset high byte"):
        _ = ch.offset_hz


def test_offset_write_clears_high_byte(blank):
    img, ch = blank
    img._buf[0x80C] = 0x01
    ch.offset_hz = 600_000
    assert img._buf[0x80C:0x80E] == bytes([0x00, 0x0C])
    assert ch.offset_hz == 600_000


@pytest.mark.parametrize("hz", [12_800_000, 620_000, -50_000])
def test_offset_rejects_unrepresentable(blank, hz):
    with pytest.raises(ValueError):
        blank[1].offset_hz = hz


@pytest.mark.parametrize("hz", [600_000.0, True, "600000"])
def test_offset_non_int_is_a_type_error_like_encode_freq(blank, hz):
    with pytest.raises(TypeError, match="offset"):
        blank[1].offset_hz = hz
    with pytest.raises(TypeError):
        encode_freq(hz)


def test_offset_extremes(blank):
    img, ch = blank
    ch.offset_hz = 12_750_000
    assert img._buf[0x80D] == 255
    ch.offset_hz = 600_000
    assert img._buf[0x80D] == 12


def test_user_ctcss_out_of_range_byte_round_trips_but_new_value_refused(blank):
    img, ch = blank
    ch.user_ctcss_hz = 0
    with pytest.raises(ValueError):
        ch.user_ctcss_hz = 200
    ch.user_ctcss_hz = 1500
    assert img._buf[0x80B] & 0x7F == 15


def test_tx_setter_requires_split(blank):
    _, ch = blank
    ch.band = Band.VHF
    ch.rx_hz = 146_700_000
    ch.shift = "-RPT"
    with pytest.raises(ValueError, match="split"):
        ch.tx_hz = 147_000_000
    ch.shift = "split"
    with pytest.raises(ValueError, match="outside band"):
        ch.tx_hz = 440_000_000
    ch.tx_hz = 147_000_000
    assert ch.tx_hz == 147_000_000


def test_band_change_revalidates_frequency(blank):
    _, ch = blank
    ch.enabled = True
    ch.retune(Band.VHF, 146_500_000)
    with pytest.raises(ValueError, match="outside band"):
        ch.band = Band.UHF
    assert (ch.band, ch.rx_hz) == (Band.VHF, 146_500_000)
    ch.retune(Band.UHF, 438_025_000)
    assert (ch.band, ch.rx_hz) == (Band.UHF, 438_025_000)


def test_retune_rejects_mismatch(blank):
    _, ch = blank
    ch.enabled = True
    ch.retune(Band.VHF, 146_500_000)
    with pytest.raises(ValueError):
        ch.retune(Band.AIR, 146_500_000)
    assert (ch.band, ch.rx_hz) == (Band.VHF, 146_500_000)   # nothing half-written


def test_band_setter_unchecked_when_disabled(blank):
    _, ch = blank
    ch.band = Band.UHF
    assert ch.band == Band.UHF


def test_retune_rawcode_band_only_grid_check(blank):
    _, ch = blank
    ch.enabled = True
    ch.retune(RawCode(5), 146_500_000)
    assert (ch.band, ch.rx_hz) == (RawCode(5), 146_500_000)
    with pytest.raises(ValueError):
        ch.retune(RawCode(6), 146_502_000)
    assert ch.band == RawCode(5)


@pytest.mark.parametrize("b", [(0x0F, 0x46, 0x50), (0x01, 0xA6, 0x50), (0x01, 0x4F, 0x50),
                               (0x01, 0x46, 0xA0), (0x01, 0x46, 0x5B)])
def test_decode_freq_rejects_non_bcd(b):
    with pytest.raises(ValueError, match="non-BCD"):
        decode_freq(*b)


# rec[2] high nibble = sub-10 kHz fraction code. Anchors are Australian UHF CB
# channels from real radio backups (standardised frequencies): CB CH1 476.4250,
# CB CH41 476.4375, CB CH42 476.4625.
@pytest.mark.parametrize("b, hz", [((0x84, 0x76, 0x42), 476_425_000),
                                   ((0xC4, 0x76, 0x43), 476_437_500),
                                   ((0x44, 0x76, 0x46), 476_462_500),
                                   ((0x01, 0x46, 0x50), 146_500_000)])
def test_decode_freq_fraction_codes(b, hz):
    assert decode_freq(*b) == hz


@pytest.mark.parametrize("code", [0x1, 0x2, 0x3, 0x5, 0x6, 0x7, 0x9, 0xA, 0xB, 0xD, 0xE, 0xF])
def test_decode_freq_refuses_undecoded_fraction_code(code):
    # never read an unproven fraction as some other frequency
    with pytest.raises(ValueError, match="fraction code"):
        decode_freq((code << 4) | 0x01, 0x46, 0x50)


@pytest.mark.parametrize("hz, b", [(476_437_500, (0xC4, 0x76, 0x43)),
                                   (476_462_500, (0x44, 0x76, 0x46)),
                                   (476_425_000, (0x84, 0x76, 0x42))])
def test_encode_freq_2k5_grid(hz, b):
    assert encode_freq(hz) == b


def test_freq_write_replaces_stale_fraction_code(blank):
    # retuning a 476.4625 channel must not keep its +2.5 kHz code
    img, ch = blank
    img._buf[CH1_REC:CH1_REC + 5] = bytes([0x83, 0x00, 0x44, 0x76, 0x46])
    ch.rx_hz = 476_500_000
    assert ch.rx_hz == 476_500_000
    assert img._buf[CH1_REC + 2] == 0x04


def test_pms_name_setter_is_value_error(blank):
    img, _ = blank
    with pytest.raises(ValueError, match="no name tag"):
        img.memory.pms[1].lower.name = "X"
    with pytest.raises(ValueError, match="no name tag"):
        img.memory.pms[1].lower.name = ""


# --- declarative field registry ----------------------------------------------

def test_fields_registry_is_single_source():
    assert len(record.FIELDS) == len(set(record.FIELDS))
    assert set(coerce.PARSERS) == set(record.FIELDS)
    alias_targets = {target for target, _ in coerce.EDGE_ALIASES.values()}
    assert alias_targets <= set(record.FIELDS)
    assert set(coerce.SETTABLE) == ((set(record.FIELDS) - alias_targets)
                                    | set(coerce.EDGE_ALIASES))
    assert type(Channel.__dict__["skip"]).__name__ == "Flag"
    assert type(Channel.__dict__["power"]).__name__ == "Code"
    for name in record.FIELDS:   # every settable field is a property or a _Field descriptor
        assert isinstance(getattr(Channel, name, None), (property, _Field)), name


# --- neutral ChannelRecord + validate-then-write ------------------------------

def test_write_record_is_all_or_nothing(blank):
    img, ch = blank
    ch.enabled = True
    ch.retune(Band.VHF, 146_500_000)
    before = bytes(img._buf)
    bad = dataclasses.replace(ch.to_record(), power="LOW", offset_hz=620_000)
    with pytest.raises(ValueError):
        write_record(ch, bad)
    assert bytes(img._buf) == before


def test_write_record_failure_in_last_field_writes_nothing(blank):
    # Every earlier field changes and validates; only the last one is bad.
    img, ch = blank
    before = bytes(img._buf)
    bad = dataclasses.replace(
        ch.to_record(), enabled=True, name="RPT", band=Band.UHF, rx_hz=438_500_000,
        shift="-RPT", offset_hz=5_000_000, power="LOW", tone_mode="TONE",
        ctcss_hz=123.0, user_ctcss_hz=12_345)
    with pytest.raises(ValueError, match="user CTCSS"):
        write_record(ch, bad)
    assert bytes(img._buf) == before


def test_record_round_trip_preserves_undecoded_bits(sample_paths, read_bytes):
    for p in sample_paths:
        img = load(CloneImage, p)
        for n in range(1, layout.NUM_REGULAR + 1):
            ch = img.memory.channels[n]
            if ch.enabled:
                write_record(ch, ch.to_record())
        assert img.to_bytes() == read_bytes(p)


def test_record_round_trip_pms_vfo_home(sample_paths, read_bytes):
    # Records with no name tag: name is None and the round trip is byte-identical.
    checked = 0
    for p in sample_paths:
        img = load(CloneImage, p)
        views = [c for pair in img.memory.pms for c in (pair.lower, pair.upper)]
        maps = (img.setup.vfo_a, img.setup.vfo_b, img.memory.home_a, img.memory.home_b)
        views += [m[b] for m in maps for b in Band]
        for ch in views:
            if ch.enabled:
                rec = ch.to_record()
                assert rec.name is None
                write_record(ch, rec)
                checked += 1
        assert img.to_bytes() == read_bytes(p)
    assert checked


def test_write_record_name_on_nameless_record_refused(blank):
    img, _ = blank
    pms = img.memory.pms[1].lower
    before = bytes(img._buf)
    with pytest.raises(ValueError, match="no name tag"):
        write_record(pms, dataclasses.replace(pms.to_record(), skip=True, name="X"))
    assert bytes(img._buf) == before


def test_to_record_split_and_offset_reporting(blank):
    _, ch = blank
    ch.enabled = True
    ch.retune(Band.VHF, 146_500_000)
    ch.offset_hz = 600_000
    ch.shift = "-RPT"
    rec = ch.to_record()
    assert (rec.shift, rec.offset_hz, rec.tx_hz) == ("-RPT", 600_000, None)
    ch.shift = "split"
    ch.tx_hz = 147_100_000
    rec = ch.to_record()
    # the stored offset byte is real data: still reported for split
    assert (rec.shift, rec.offset_hz, rec.tx_hz) == ("split", 600_000, 147_100_000)
    assert isinstance(rec.name, str) and rec.band is Band.VHF and rec.step == 5.0


def test_write_record_none_fields_preserve_bits(blank):
    img, ch = blank
    ch.enabled = True
    ch.name = "KEEP"
    ch.retune(Band.VHF, 146_500_000)
    ch.offset_hz = 600_000
    img._buf[CH1_REC + 9] |= 0x3f       # CTCSS index out of table
    img._buf[CH1_REC + 10] |= 0x7f      # DCS index out of table
    before = bytes(img._buf)
    rec = ch.to_record()
    assert rec.ctcss_hz is None and rec.dcs is None
    write_record(ch, dataclasses.replace(rec, name=None, offset_hz=None, tx_hz=None))
    assert bytes(img._buf) == before


def test_write_record_applies_shift_before_tx(blank):
    _, ch = blank
    ch.enabled = True
    ch.retune(Band.VHF, 146_500_000)
    write_record(ch, dataclasses.replace(ch.to_record(), shift="split", tx_hz=147_000_000,
                                         offset_hz=None))
    assert (ch.shift, ch.tx_hz) == ("split", 147_000_000)


def test_write_record_raw_codes_pass_through(blank):
    img, ch = blank
    img._buf[CH1_REC + 0] = 0x80 | 0x05             # enabled, undecoded band 5
    img._buf[CH1_REC + 1] = 0x40 | 0x07             # undecoded rec[1] 0x40 bit, shift 7
    img._buf[CH1_REC + 2] = 0xC1                    # fraction code C (+7.5 kHz), 1xx MHz
    img._buf[CH1_REC + 3] = 0x46
    img._buf[CH1_REC + 5] = 0x3f                    # tone mode 3, step 15
    img._buf[CH1_REC + 9] = 0xc0                    # power 3
    for i in (14, 15):
        img._buf[CH1_REC + i] = 0xa5
    before = bytes(img._buf)
    rec = ch.to_record()
    assert rec.band == RawCode(5) and isinstance(rec.band, RawCode)
    assert all(isinstance(v, RawCode) for v in (rec.shift, rec.tone_mode, rec.step, rec.power))
    write_record(ch, rec)
    assert bytes(img._buf) == before


def test_write_record_disabled_blank_round_trips(blank):
    # Unchanged band+rx skips retune, so an all-zero disabled record
    # (AIR, 0 Hz: outside AIR's range) round-trips byte-identically.
    img, ch = blank
    before = bytes(img._buf)
    write_record(ch, ch.to_record())
    assert bytes(img._buf) == before


def test_write_record_enables_disabled_record(blank):
    _, ch = blank
    write_record(ch, dataclasses.replace(ch.to_record(), enabled=True, band=Band.VHF,
                                         rx_hz=146_500_000))
    assert (ch.enabled, ch.band, ch.rx_hz) == (True, Band.VHF, 146_500_000)


def test_write_record_changed_rx_still_validated(blank):
    img, ch = blank
    before = bytes(img._buf)
    with pytest.raises(ValueError, match="outside band"):
        write_record(ch, dataclasses.replace(ch.to_record(), rx_hz=146_500_000))  # AIR
    assert bytes(img._buf) == before


def test_write_record_enabling_revalidates_unchanged_band_rx(blank):
    # R13 amended: enabling a disabled record never skips retune.
    img, ch = blank
    before = bytes(img._buf)
    with pytest.raises(ValueError, match="outside band AIR"):
        write_record(ch, dataclasses.replace(ch.to_record(), enabled=True))
    assert bytes(img._buf) == before


@pytest.mark.parametrize("mode", ["XYZ", "am", ""])
def test_write_record_validates_mode(blank, mode):
    img, ch = blank
    ch.enabled = True
    ch.retune(Band.VHF, 146_500_000)
    before = bytes(img._buf)
    with pytest.raises(ValueError, match="AM or FM"):
        write_record(ch, dataclasses.replace(ch.to_record(), mode=mode, skip=True))
    assert bytes(img._buf) == before


@pytest.mark.parametrize("code", [0, 1, 2, 3])
def test_decoded_band_code_is_normalised_to_band(blank, code):
    """RawCode(0..3) names a decoded band: stored and validated as that Band (I1)."""
    assert parse_band(str(code)) is Band(code)
    _, ch = blank
    ch.band = RawCode(code)
    assert ch.band is Band(code)


def test_decoded_band_code_is_range_checked(blank):
    _, ch = blank
    ch.retune(Band.VHF, 146_650_000)
    ch.enabled = True
    with pytest.raises(ValueError, match="outside band UHF"):
        ch.band = RawCode(3)
    with pytest.raises(ValueError, match="outside band UHF"):
        ch.retune(RawCode(3), 146_650_000)
    assert ch.band is Band.VHF


def test_undecoded_band_code_stays_raw():
    b = parse_band("6")
    assert b == 6 and type(b) is RawCode


def test_name_longer_than_8_refused(blank):
    _, ch = blank
    ch.name = "A" * 8
    assert ch.name == "A" * 8
    with pytest.raises(ValueError, match="name longer than 8 characters"):
        ch.name = "A" * 9
    assert ch.name == "A" * 8


def _stored_long_tag(blank):
    img, ch = blank
    tag = b"TWELVE-CHARS"
    img._buf[layout.NAME_BASE:layout.NAME_BASE + 16] = tag + b"\xff" * 4
    return img, ch, tag.decode()


def test_stored_long_tag_survives_self_assignment(blank):
    img, ch, tag = _stored_long_tag(blank)
    before = bytes(img._buf)
    ch.name = tag
    assert ch.name == tag and bytes(img._buf) == before


def test_setting_same_name_repairs_the_present_word(blank):
    img, ch = blank
    nf = layout.NAME_FLAG_BASE
    tag = bytes(img._buf[layout.NAME_BASE:layout.NAME_BASE + 16])
    img._buf[layout.NAME_BASE:layout.NAME_BASE + 16] = b"ABC" + b"\xff" * 13
    img._buf[nf:nf + 2] = b"\xff\xff"
    ch.name = "ABC"
    assert bytes(img._buf[nf:nf + 2]) == b"\x00\x00"
    assert bytes(img._buf[layout.NAME_BASE:layout.NAME_BASE + 16]) == b"ABC" + b"\xff" * 13
    img._buf[layout.NAME_BASE:layout.NAME_BASE + 16] = b"\xff" * 16
    img._buf[nf:nf + 2] = b"\x00\x00"
    assert ch.name == "" and tag is not None
    ch.name = ""
    assert bytes(img._buf[nf:nf + 2]) == b"\xff\xff"


def test_stored_long_tag_survives_write_record(blank):
    img, ch, _tag = _stored_long_tag(blank)
    before = bytes(img._buf)
    write_record(ch, ch.to_record())
    assert bytes(img._buf) == before


def test_show_name_descriptor_is_documented():
    doc = Channel.show_name.__doc__ or ""
    assert "name" in doc and "frequency" in doc
