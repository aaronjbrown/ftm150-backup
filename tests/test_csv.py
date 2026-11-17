import csv
import dataclasses
import os
from pathlib import Path

import pytest

from ftm150 import CloneImage, csv_io, ops
from ftm150.engine import layout
from ftm150.engine.record import write_record
from ftm150.engine.tables import Band, RawCode
from ftm150.ops import save_image
from tests.files import ALL_A, load


def _save(img, path):
    save_image(img, str(path))
    return str(path)


def _export(img, tmp_path, name="e.csv"):
    """Export an in-memory image's CSV through ops; return the CSV path."""
    ops.export_csv(_save(img, tmp_path / "src.dat"), str(tmp_path / name))
    return str(tmp_path / name)


def _import(img, csv_path, tmp_path):
    """Import a CSV onto an in-memory image through ops; return the result image."""
    ops.import_csv(_save(img, tmp_path / "base.dat"), csv_path, str(tmp_path / "res.dat"))
    return load(CloneImage, str(tmp_path / "res.dat"))


def _dirty(img):
    """Set skip, mgrp, clock_shift, narrow and show_name on every channel, so an
    import that only sets bits (never clears them) leaves visible residue."""
    for n in range(1, layout.NUM_REGULAR + 1):
        ch = img.memory.channels[n]
        ch.skip = ch.mgrp = ch.clock_shift = ch.narrow = ch.show_name = True
    return img


def test_export_has_header_and_first_channel(tmp_path):
    img = load(CloneImage, ALL_A)
    text = Path(_export(img, tmp_path)).read_text()
    lines = text.splitlines()
    assert lines[0].split(",")[:3] == ["Location", "Name", "Frequency"]
    assert "RPT2M-A" in lines[1]
    assert "146.9" in lines[1]


def test_csv_round_trip_reproduces_channel_bytes(tmp_path):
    img = load(CloneImage, ALL_A)
    img2 = _import(load(CloneImage, ALL_A), _export(img, tmp_path), tmp_path)   # same base
    for n in range(1, layout.NUM_REGULAR + 1):
        a, b = img.memory.channels[n], img2.memory.channels[n]
        if a.enabled:
            assert a.raw == b.raw, n
            assert a.name == b.name, n


def test_csv_cross_base_preserves_decoded_fields(tmp_path):
    src = load(CloneImage, ALL_A)
    dst = _import(_dirty(CloneImage(bytes(0x18000))),   # different base, flags all set
                  _export(src, tmp_path), tmp_path)
    fields = ["name","band","rx_hz","tx_hz","shift","offset_hz","mode","narrow",
              "tone_mode","ctcss_hz","dcs","power","step_khz","skip","mgrp",
              "clock_shift","user_ctcss_hz","show_name"]
    assert {src.memory.channels[n].show_name for n in range(1, layout.NUM_REGULAR + 1)
            if src.memory.channels[n].enabled} == {True, False}   # ALL_A mixes both
    for n in range(1, layout.NUM_REGULAR + 1):
        if src.memory.channels[n].enabled:
            a, b = src.memory.channels[n], dst.memory.channels[n]
            assert b.enabled, (n, "enabled")
            for f in fields:
                assert getattr(a, f) == getattr(b, f), (n, f)


def test_csv_roundtrip_survives_out_of_range_tone_index(tmp_path):
    img = load(CloneImage, ALL_A)
    # poke channel 1's rec[9] low 6 bits to an out-of-range CTCSS index (>= 50)
    off = 0x800 + 0 * 0x10
    img._buf[off + 9] = (img._buf[off + 9] & 0xC0) | 60  # index 60, no table entry
    assert img.memory.channels[1].ctcss_hz is None
    before = img.memory.channels[1].raw
    img2 = _import(CloneImage(bytes(img._buf)), _export(img, tmp_path), tmp_path)  # must not raise
    assert img2.memory.channels[1].raw == before       # byte-preserved (tone skipped)


def test_csv_without_showname_column_keeps_base_display(tmp_path):
    # CSVs written before the ShowName column existed must still import.
    img = load(CloneImage, ALL_A)
    lines = Path(_export(img, tmp_path)).read_text().splitlines()
    idx = lines[0].split(",").index("ShowName")
    legacy = "\n".join(",".join(c for i, c in enumerate(line.split(",")) if i != idx)
                       for line in lines)
    before = {n: img.memory.channels[n].show_name for n in range(1, layout.NUM_REGULAR + 1)}
    legacy_path = tmp_path / "legacy.csv"
    legacy_path.write_text(legacy)
    res = _import(img, str(legacy_path), tmp_path)
    assert {n: res.memory.channels[n].show_name for n in range(1, layout.NUM_REGULAR + 1)} == before


def test_csv_raw_codes_survive_cross_base_round_trip(blank):
    img, ch = blank
    ch.band = Band.VHF
    ch.rx_hz = 146_500_000
    ch.enabled = True
    ch.user_ctcss_hz = 1500
    img._buf[0x801] = (img._buf[0x801] & ~0x07) | 5
    img._buf[0x809] = 0xC0
    img._buf[0x805] = (img._buf[0x805] & 0x0F) | 0x30
    row = csv_io.record_to_row(1, ch.to_record())
    assert row["Duplex"] == "5" and row["TxPower"] == "3" and row["Tone"] == "3"
    fresh = CloneImage(bytes(0x18000)).memory.channels[1]
    write_record(fresh, csv_io.row_to_record(_text(row), show_name_default=False))
    assert fresh.shift == 5 and fresh.power == 3 and fresh.tone_mode == 3


def test_csv_raw_band_round_trip(blank):
    img, ch = blank
    img._buf[0x800] = 0x06
    ch.enabled = True
    ch.rx_hz = 146_500_000
    ch.user_ctcss_hz = 1500
    row = csv_io.record_to_row(1, ch.to_record())
    assert row["Band"] == "6"
    fresh = CloneImage(bytes(0x18000)).memory.channels[1]
    write_record(fresh, csv_io.row_to_record(_text(row), show_name_default=False))
    assert fresh.band == 6 and isinstance(fresh.band, RawCode)
    assert fresh.rx_hz == 146_500_000


def test_csv_refuses_unknown_step(blank):
    img, ch = blank
    ch.band = Band.VHF
    ch.rx_hz = 146_500_000
    ch.enabled = True
    img._buf[0x805] = (img._buf[0x805] & 0xF0) | 12
    with pytest.raises(ValueError, match="CH1: unknown step code 12"):
        csv_io.record_to_row(1, ch.to_record())


def test_csv_refuses_step_code_2(blank):
    img, ch = blank
    ch.band = Band.VHF
    ch.rx_hz = 146_500_000
    ch.enabled = True
    img._buf[0x805] = (img._buf[0x805] & 0xF0) | 2
    with pytest.raises(ValueError, match="unknown step code 2"):
        csv_io.record_to_row(1, ch.to_record())


def test_csv_import_auto_step_refused(tmp_path):
    out = tmp_path / "o.dat"
    with pytest.raises(ValueError, match=r"CH1: .*no AUTO step"):
        ops.import_csv(ALL_A, _write_csv([_row(TStep="AUTO")], tmp_path), str(out))
    assert not out.exists()


def _text(row):
    """A row as csv.DictReader yields it: every value a string."""
    return {k: str(v) for k, v in row.items()}


_ENUMS = ("band", "shift", "tone_mode", "power", "step")


def test_row_record_round_trip(sample_paths):
    for path in sample_paths:
        img = load(CloneImage, path)
        for n in range(1, layout.NUM_REGULAR + 1):
            ch = img.memory.channels[n]
            if not ch.enabled:
                continue
            want = ch.to_record()
            if want.shift == "split":       # a split row carries tx, not offset
                want = dataclasses.replace(want, offset_hz=None)
            row = _text(csv_io.record_to_row(n, ch.to_record()))
            got = csv_io.row_to_record(row, show_name_default=not want.show_name)
            assert got == want, (path, n)
            for f in _ENUMS:                # Band.VHF == RawCode(1): check types too
                assert type(getattr(got, f)) is type(getattr(want, f)), (path, n, f)


def _row(**over):
    img = load(CloneImage, ALL_A)
    return {**_text(csv_io.record_to_row(1, img.memory.channels[1].to_record())), **over}


def test_row_to_record_normalises_edge_text():
    rec = csv_io.row_to_record(_row(Mode=" fm ", Band=" VHF ", Duplex=" - ",
                                    TxPower=" HIGH ", TStep=" 25.0 ", Tone=" Tone "),
                              show_name_default=False)
    assert (rec.mode, rec.band, rec.shift, rec.power, rec.step, rec.tone_mode) == (
        "FM", Band.VHF, "-RPT", "HIGH", 25.0, "TONE")


def test_row_to_record_refuses_unknown_mode():
    with pytest.raises(ValueError, match="Mode"):
        csv_io.row_to_record(_row(Mode="USB"), show_name_default=False)


def test_row_to_record_blank_tones_are_not_carried():
    rec = csv_io.row_to_record(_row(rToneFreq="", DtcsCode=""), show_name_default=False)
    assert rec.ctcss_hz is None and rec.dcs is None


def test_import_csv_goes_through_write_record_atomically(tmp_path):
    # A bad field late in the row leaves the channel byte-identical (whole-record
    # validation), not half-written by the fields before it.
    row = _row(Frequency="146.5", UserCTCSS="12345")
    with pytest.raises(ValueError):
        ops.import_csv(ALL_A, _write_csv([row], tmp_path), str(tmp_path / "o.dat"))
    assert not (tmp_path / "o.dat").exists()


def _write_csv(rows, tmp_path, name="w.csv"):
    path = tmp_path / name
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=csv_io.CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return str(path)


@pytest.mark.parametrize("cell", ["", None])     # blank, or the column absent
def test_row_to_record_show_name_default(cell):
    row = _row()
    if cell is None:
        del row["ShowName"]
    else:
        row["ShowName"] = cell
    for default in (True, False):
        assert csv_io.row_to_record(row, show_name_default=default).show_name is default
    assert csv_io.row_to_record(_row(ShowName="1"), show_name_default=False).show_name is True


def test_import_csv_errors_name_the_channel(tmp_path):
    with pytest.raises(ValueError, match="CH1: Mode"):
        ops.import_csv(ALL_A, _write_csv([_row(Mode="USB")], tmp_path),
                       str(tmp_path / "o.dat"))


_DECODED = ("enabled", "name", "band", "rx_hz", "shift", "offset_hz", "tx_hz", "mode",
            "narrow", "tone_mode", "ctcss_hz", "dcs", "step", "power", "skip", "mgrp",
            "clock_shift", "user_ctcss_hz", "show_name")


def test_csv_cross_base_import_matches_row_records(sample_paths, tmp_path):
    """Every fixture's CSV imported onto a different base (ALL_A, or a blank
    image for ALL_A itself) yields exactly the records its rows describe."""
    for path in sample_paths:
        src = load(CloneImage, path)
        rows = [_text(csv_io.record_to_row(n, src.memory.channels[n].to_record()))
                for n in range(1, layout.NUM_REGULAR + 1) if src.memory.channels[n].enabled]
        same = os.path.samefile(path, ALL_A)
        dst = _dirty(CloneImage(bytes(0x18000)) if same else load(CloneImage, ALL_A))
        base_show = {int(r["Location"]): dst.memory.channels[int(r["Location"])].show_name
                     for r in rows}
        dst = _import(dst, _write_csv(rows, tmp_path), tmp_path)
        for row in rows:
            n = int(row["Location"])
            got = dst.memory.channels[n].to_record()
            want = csv_io.row_to_record(row, show_name_default=base_show[n])
            for f in _DECODED:
                w = getattr(want, f)
                if w is None:                   # not carried, target bits kept
                    continue
                assert getattr(got, f) == w, (path, n, f)
                if f in _ENUMS:
                    assert type(getattr(got, f)) is type(w), (path, n, f)


def _one_row_csv(path, row):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=csv_io.CSV_COLUMNS)
        w.writeheader()
        w.writerow(row)


def _vhf_row(blank, **over):
    _, ch = blank
    ch.retune(Band.VHF, 146_650_000)
    ch.enabled = True
    ch.user_ctcss_hz = 1500
    return {**_text(csv_io.record_to_row(1, ch.to_record())), **over}


def test_csv_digit_band_is_range_checked(blank, tmp_path):
    """Band "3" (UHF's code) on a VHF frequency is refused like Band "UHF" (I1)."""
    csvf, out = tmp_path / "c.csv", tmp_path / "o.dat"
    _one_row_csv(csvf, _vhf_row(blank, Band="3"))
    base = tmp_path / "b.dat"
    save_image(CloneImage(bytes(0x18000)), str(base))
    with pytest.raises(ValueError, match=r"^CH1: .*outside band UHF"):
        ops.import_csv(str(base), str(csvf), str(out))
    assert not out.exists()


def test_csv_digit_band_in_range_reads_back_as_band(blank, tmp_path):
    row = _vhf_row(blank, Band="3", Frequency="438.5")
    assert csv_io.row_to_record(row, show_name_default=False).band is Band.UHF
    csvf, out, base = tmp_path / "c.csv", tmp_path / "o.dat", tmp_path / "b.dat"
    _one_row_csv(csvf, row)
    save_image(CloneImage(bytes(0x18000)), str(base))
    ops.import_csv(str(base), str(csvf), str(out))
    ch = load(CloneImage, str(out)).memory.channels[1]
    assert ch.band is Band.UHF and ch.rx_hz == 438_500_000


def test_csv_long_name_refused(blank, tmp_path):
    """A 9-character Name is refused with the CH prefix, not truncated."""
    csvf, out, base = tmp_path / "c.csv", tmp_path / "o.dat", tmp_path / "b.dat"
    _one_row_csv(csvf, _vhf_row(blank, Name="A" * 9))
    save_image(CloneImage(bytes(0x18000)), str(base))
    with pytest.raises(ValueError, match=r"^CH1: name longer than 8 characters"):
        ops.import_csv(str(base), str(csvf), str(out))
    assert not out.exists()


def test_csv_malformed_file_is_a_value_error(blank, tmp_path):
    """csv.Error (here: a field over csv.field_size_limit) surfaces as ValueError (M5)."""
    csvf, out, base = tmp_path / "c.csv", tmp_path / "o.dat", tmp_path / "b.dat"
    row = _vhf_row(blank)
    _one_row_csv(csvf, {**row, "Name": "x" * (csv.field_size_limit() + 1)})
    save_image(CloneImage(bytes(0x18000)), str(base))
    with pytest.raises(ValueError, match=r"CSV line \d+: .*field larger than field limit"):
        ops.import_csv(str(base), str(csvf), str(out))
    assert not out.exists()


def _long_tag_image():
    """An image whose CH1 is valid and enabled but carries a stored 12-character tag."""
    img = CloneImage(bytes(0x18000))
    ch = img.memory.channels[1]
    ch.retune(Band.VHF, 146_650_000)
    ch.enabled = True
    ch.user_ctcss_hz = 1500
    img._buf[layout.NAME_BASE:layout.NAME_BASE + 16] = b"TWELVE-CHARS" + b"\xff" * 4
    img._buf[layout.NAME_FLAG_BASE:layout.NAME_FLAG_BASE + 2] = b"\x00\x00"
    return img


@pytest.mark.parametrize("chirp", [False, True])
def test_stored_long_tag_same_base_round_trip_is_byte_identical(tmp_path, chirp):
    img = _long_tag_image()
    base, csvf, out = (tmp_path / n for n in ("b.dat", "c.csv", "o.dat"))
    save_image(img, str(base))
    ops.export_csv(str(base), str(csvf), chirp=chirp)
    ops.import_csv(str(base), str(csvf), str(out), chirp=chirp)
    assert out.read_bytes() == base.read_bytes()


@pytest.mark.parametrize("chirp", [False, True])
def test_stored_long_tag_cross_base_import_is_refused(tmp_path, chirp):
    src, base, csvf, out = (tmp_path / n for n in ("s.dat", "b.dat", "c.csv", "o.dat"))
    save_image(_long_tag_image(), str(src))
    save_image(CloneImage(bytes(0x18000)), str(base))
    ops.export_csv(str(src), str(csvf), chirp=chirp)
    with pytest.raises(ValueError, match="name longer than 8 characters"):
        ops.import_csv(str(base), str(csvf), str(out), chirp=chirp)
    assert not out.exists()
