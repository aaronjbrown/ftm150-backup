import csv
import json
import os

import pytest

from ftm150 import CloneImage, MemoryImage, NotInBackup, SetupImage, chirp, csv_io, ops
from ftm150.engine.partial import Kind
from ftm150.ops import save_image
from tests.files import ALL_A, ALL_B, MEMORY_B, SETUP_B, load
from tests.test_chirp import UHF, VHF


def read(path):
    with open(path, "rb") as fh:
        return fh.read()


def test_set_field_requires_out_or_in_place(tmp_path):
    f = tmp_path / "a.dat"
    f.write_bytes(read(ALL_B))
    with pytest.raises(ValueError, match="output path is required"):
        ops.set_field(str(f), 1, "power", "LOW")
    ops.set_field(str(f), 1, "power", "LOW", in_place=True)
    assert load(CloneImage, str(f)).memory.channels[1].power == "LOW"


def test_set_field_refuses_out_with_in_place(tmp_path):
    f = tmp_path / "a.dat"
    f.write_bytes(read(ALL_B))
    out = tmp_path / "o.dat"
    with pytest.raises(ValueError, match="not both"):
        ops.set_field(str(f), 1, "power", "LOW", str(out), in_place=True)
    assert not out.exists()
    assert read(str(f)) == read(ALL_B)
    with pytest.raises(ValueError, match="not both"):     # checked before loading
        ops.set_field(str(tmp_path / "missing.dat"), 1, "power", "LOW", str(out),
                      in_place=True)


def test_import_csv_validates_before_writing(tmp_path):
    csvf = tmp_path / "c.csv"
    out = tmp_path / "o.dat"
    good = csv_io.record_to_row(1, load(CloneImage, ALL_B).memory.channels[1].to_record())
    bad = {**good, "Location": "2", "Frequency": "146.65125"}
    with open(csvf, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=csv_io.CSV_COLUMNS)
        w.writeheader()
        w.writerows([good, bad])
    with pytest.raises(ValueError):
        ops.import_csv(ALL_B, str(csvf), str(out))
    assert not out.exists()


def _chirp_csv(path, rows):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=chirp.CHIRP_COLUMNS)
        w.writeheader()
        w.writerows(rows)


def test_chirp_import_defaults_only_for_empty_target(tmp_path):
    base, mid, out = (str(tmp_path / n) for n in ("b.dat", "m.dat", "o.dat"))
    save_image(CloneImage(bytes(0x18000)), base)
    _chirp_csv(tmp_path / "one.csv", [VHF])                     # CH6 only
    ops.import_csv(base, str(tmp_path / "one.csv"), mid, chirp=True)
    ops.set_field(mid, 6, "power", "LOW", in_place=True)        # CH6 now occupied, power LOW
    _chirp_csv(tmp_path / "two.csv", [UHF, VHF])                # CH5 empty, CH6 occupied
    ops.import_csv(mid, str(tmp_path / "two.csv"), out, chirp=True)
    out_img = load(CloneImage, out)
    assert out_img.memory.channels[5].power == "HIGH" and out_img.memory.channels[6].power == "LOW"


def test_chirp_import_tone_off_keeps_base_tone_bits(tmp_path):
    base, mid, out = (str(tmp_path / n) for n in ("b.dat", "m.dat", "o.dat"))
    save_image(CloneImage(bytes(0x18000)), base)
    _chirp_csv(tmp_path / "one.csv", [UHF])                     # CH5: Tone 91.5
    ops.import_csv(base, str(tmp_path / "one.csv"), mid, chirp=True)
    ops.set_field(mid, 5, "dcs", "754", in_place=True)
    _chirp_csv(tmp_path / "off.csv", [{**UHF, "Tone": "", "rToneFreq": "", "cToneFreq": "",
                                       "DtcsCode": ""}])
    ops.import_csv(mid, str(tmp_path / "off.csv"), out, chirp=True)
    ch = load(CloneImage, out).memory.channels[5]
    assert (ch.tone_mode, ch.ctcss_hz, ch.dcs) == ("OFF", 91.5, 754)


def test_native_import_rebands_occupied_vhf_channel_to_uhf(tmp_path):
    csvf, out = tmp_path / "c.csv", tmp_path / "o.dat"
    before = load(CloneImage, ALL_B)
    assert before.memory.channels[1].enabled and before.memory.channels[1].band.name == "VHF"
    _native_csv(csvf, [_all_b_row(1, Band="UHF", Frequency="438.025", Offset="7.000")])
    assert ops.import_csv(ALL_B, str(csvf), str(out)).rows == 1
    after = load(CloneImage, str(out))
    ch = after.memory.channels[1]
    assert (ch.band.name, ch.rx_hz, ch.shift, ch.offset_hz, ch.name) == (
        "UHF", 438_025_000, "-RPT", 7_000_000, "RPT2M-A")
    assert all(after.memory.channels[n].raw == before.memory.channels[n].raw
               for n in range(2, 1000))


def test_native_import_duplicate_location_last_row_wins(tmp_path):
    csvf, out = tmp_path / "c.csv", tmp_path / "o.dat"
    _native_csv(csvf, [_all_b_row(1, Name="FIRST", TxPower="LOW"),
                       _all_b_row(1, Name="SECOND")])
    assert ops.import_csv(ALL_B, str(csvf), str(out)).rows == 2
    ch = load(CloneImage, str(out)).memory.channels[1]
    assert (ch.name, ch.power) == ("SECOND", load(CloneImage, ALL_B).memory.channels[1].power)


def test_chirp_import_duplicate_location_last_wins_and_defaults_hold(tmp_path):
    base, out = str(tmp_path / "b.dat"), str(tmp_path / "o.dat")
    img = CloneImage(bytes(0x18000))
    img.memory.channels[5].power = "LOW"           # stale bits on a disabled channel
    img.memory.channels[5].mgrp = True
    save_image(img, base)
    _chirp_csv(tmp_path / "u.csv", [UHF, {**UHF, "Name": "SECOND", "Frequency": "439.000000"}])
    assert ops.import_csv(base, str(tmp_path / "u.csv"), out, chirp=True).rows == 2
    ch = load(CloneImage, out).memory.channels[5]
    assert (ch.name, ch.rx_hz, ch.enabled) == ("SECOND", 439_000_000, True)
    assert (ch.power, ch.mgrp, ch.clock_shift, ch.user_ctcss_hz) == ("HIGH", False, False, 1500)


# --- beyond the brief -------------------------------------------------------

def _native_csv(path, rows):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=csv_io.CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)


def _all_b_row(n, **over):
    rec = load(CloneImage, ALL_B).memory.channels[n].to_record()
    return {**csv_io.record_to_row(n, rec), **over}


def test_import_csv_parse_error_raises_before_any_write_record(tmp_path, monkeypatch):
    """A row that fails to parse (row 2) aborts before row 1 is written at all."""
    csvf, out = tmp_path / "c.csv", tmp_path / "o.dat"
    _native_csv(csvf, [_all_b_row(1), _all_b_row(1, Location="2", Mode="XX")])
    calls = []
    monkeypatch.setattr(ops, "write_record", lambda ch, rec: calls.append(ch.number))
    with pytest.raises(ValueError, match=r"^CH2: "):
        ops.import_csv(ALL_B, str(csvf), str(out))
    assert calls == [] and not out.exists()


def test_import_csv_in_place_failure_leaves_file_identical(tmp_path):
    f, csvf = tmp_path / "a.dat", tmp_path / "c.csv"
    f.write_bytes(read(ALL_B))
    _native_csv(csvf, [_all_b_row(1, Name="CHANGED"),
                       _all_b_row(1, Location="2", Frequency="146.65125")])
    with pytest.raises(ValueError, match=r"^CH2: "):
        ops.import_csv(str(f), str(csvf), None, in_place=True)
    assert f.read_bytes() == read(ALL_B)


def test_import_csv_same_base_is_byte_identical(tmp_path):
    csvf, out = tmp_path / "c.csv", tmp_path / "o.dat"
    n = ops.export_csv(ALL_B, str(csvf))
    assert n == len(ops.rows(ALL_B))
    assert ops.import_csv(ALL_B, str(csvf), str(out)) == (n, str(out))
    assert out.read_bytes() == read(ALL_B)


def test_import_csv_refuses_out_equal_to_csv_or_base(tmp_path):
    csvf = tmp_path / "c.csv"
    ops.export_csv(ALL_B, str(csvf))
    before = csvf.read_bytes()
    with pytest.raises(ValueError, match="differ from every input"):
        ops.import_csv(ALL_B, str(csvf), str(csvf))
    assert csvf.read_bytes() == before
    with pytest.raises(ValueError, match="--in-place"):
        ops.import_csv(ALL_B, str(csvf), ALL_B)


def test_export_csv_refuses_in_place_and_counts_rows(tmp_path):
    f = tmp_path / "a.dat"
    f.write_bytes(read(ALL_B))
    with pytest.raises(ValueError):
        ops.export_csv(str(f), str(f))
    out = tmp_path / "c.csv"
    n = ops.export_csv(str(f), str(out), chirp=True)
    with open(out, newline="") as fh:
        got = list(csv.DictReader(fh))
    assert n == len(got) == len(ops.rows(ALL_B))
    assert list(got[0]) == chirp.CHIRP_COLUMNS
    assert f.read_bytes() == read(ALL_B)


def test_chirp_import_empty_target_takes_defaults_and_enables(tmp_path):
    base, out = str(tmp_path / "b.dat"), str(tmp_path / "o.dat")
    img = CloneImage(bytes(0x18000))
    img.memory.channels[5].power = "LOW"           # stale bits on a disabled channel
    img.memory.channels[5].mgrp = True
    save_image(img, base)
    _chirp_csv(tmp_path / "u.csv", [UHF])
    assert ops.import_csv(base, str(tmp_path / "u.csv"), out, chirp=True) == (1, out)
    ch = load(CloneImage, out).memory.channels[5]
    assert ch.enabled and ch.rx_hz == 438_025_000
    assert (ch.power, ch.mgrp, ch.clock_shift, ch.user_ctcss_hz) == ("HIGH", False, False, 1500)


def test_chirp_import_keeps_target_show_name(tmp_path):
    base, mid, out = (str(tmp_path / n) for n in ("b.dat", "m.dat", "o.dat"))
    save_image(CloneImage(bytes(0x18000)), base)
    _chirp_csv(tmp_path / "u.csv", [UHF])
    ops.import_csv(base, str(tmp_path / "u.csv"), mid, chirp=True)
    ops.set_field(mid, 5, "show_name", "1", in_place=True)
    ops.import_csv(mid, str(tmp_path / "u.csv"), out, chirp=True)
    assert load(CloneImage, out).memory.channels[5].show_name is True


def test_set_field_returns_mcp_shape_and_refuses_input(tmp_path):
    out = str(tmp_path / "o.dat")
    assert ops.set_field(ALL_B, 1, "rx_mhz", "146.6", out) == {
        "channel": 1, "field": "rx_mhz", "value": "146.6", "out_path": out}
    assert load(CloneImage, out).memory.channels[1].rx_hz == 146_600_000
    with pytest.raises(ValueError):
        ops.set_field(ALL_B, 1, "power", "LOW", ALL_B)


def test_info_and_rows():
    img = load(CloneImage, ALL_B)
    assert ops.info(ALL_B) == {
        "kind": "ALL", "magic_ok": img.magic_ok, "regular_channels": 999,
        "used": sum(1 for c in img.memory.channels if c.enabled),
        "pms_pairs": len(img.memory.pms), "apo": img.setup.settings.apo}
    assert ops.rows(ALL_B) == [csv_io.record_to_row(n, ch.to_record())
                               for n, ch in img.memory.channels.items() if ch.enabled]


def test_apply_specs_out_path_and_never_overwrites(tmp_path):
    spec = {"name": "N0CALL", "rx_frequency_mhz": "146.700", "tx_frequency_mhz": "146.100",
            "mode": "FM", "source_id": "XX:42"}
    out = str(tmp_path / "o.dat")
    res = ops.apply_specs(ALL_B, [spec], out, start=200)
    assert res.out_path == out and [a.channel for a in res.applied] == [200]
    with pytest.raises(ValueError):
        ops.apply_specs(ALL_B, [spec], ALL_B, start=200)


def test_apply_specs_past_last_channel_writes_nothing(tmp_path):
    spec = {"name": "X", "rx_frequency_mhz": "146.700", "tx_frequency_mhz": "146.100",
            "mode": "FM"}
    out = tmp_path / "o.dat"
    with pytest.raises(ValueError, match="run past channel 999"):
        ops.apply_specs(ALL_B, [spec, spec], str(out), start=999)
    assert not out.exists()


@pytest.mark.parametrize("loc", ["abc", "", "0", "1000", "-3", "1.5", "+5", "1_0",
                                 "\u0663", "\uff15"])
def test_import_csv_bad_location_names_the_value(tmp_path, loc):
    csvf, out = tmp_path / "c.csv", tmp_path / "o.dat"
    _native_csv(csvf, [_all_b_row(1, Location=loc)])
    with pytest.raises(ValueError, match=r"Location .*not a channel number 1\.\.999"):
        ops.import_csv(ALL_B, str(csvf), str(out))
    assert not out.exists()


def test_import_csv_location_allows_surrounding_space(tmp_path):
    csvf, out = tmp_path / "c.csv", tmp_path / "o.dat"
    _native_csv(csvf, [_all_b_row(1, Location=" 1 ")])
    assert ops.import_csv(ALL_B, str(csvf), str(out)).rows == 1


def test_import_csv_missing_location_column(tmp_path):
    csvf, out = tmp_path / "c.csv", tmp_path / "o.dat"
    row = _all_b_row(1)
    del row["Location"]
    with open(csvf, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[c for c in csv_io.CSV_COLUMNS if c != "Location"])
        w.writeheader()
        w.writerow(row)
    with pytest.raises(ValueError, match="CSV has no Location column"):
        ops.import_csv(ALL_B, str(csvf), str(out))


def test_import_csv_chirp_bad_location_is_range_checked(tmp_path):
    csvf, out = tmp_path / "c.csv", tmp_path / "o.dat"
    ops.export_csv(ALL_B, str(csvf), chirp=True)
    text = csvf.read_text().replace("\n1,", "\n1000,", 1)
    csvf.write_text(text)
    with pytest.raises(ValueError, match=r"Location .*1\.\.999"):
        ops.import_csv(ALL_B, str(csvf), str(out), chirp=True)
    assert not out.exists()


def test_import_csv_tolerates_bom(tmp_path):
    csvf, out = tmp_path / "c.csv", tmp_path / "o.dat"
    ops.export_csv(ALL_B, str(csvf))
    csvf.write_bytes(b"\xef\xbb\xbf" + csvf.read_bytes())
    ops.import_csv(ALL_B, str(csvf), str(out))
    assert out.read_bytes() == read(ALL_B)


def test_memory_of_and_setup_of():
    clone = load(CloneImage, ALL_B)
    assert ops.memory_of(clone) is clone.memory and ops.setup_of(clone) is clone.setup
    mem, setup = load(MemoryImage, MEMORY_B), load(SetupImage, SETUP_B)
    assert ops.memory_of(mem) is mem and ops.setup_of(setup) is setup
    with pytest.raises(NotInBackup, match="SETUP backup has no memory channels"):
        ops.memory_of(setup)
    with pytest.raises(NotInBackup, match="MEMORY backup has no settings"):
        ops.setup_of(mem)


def test_info_per_kind():
    mem = ops.info(MEMORY_B)
    assert mem["kind"] == "MEMORY" and mem["apo"] is None and mem["regular_channels"] == 999
    assert mem["used"] == ops.info(ALL_B)["used"]
    setup = ops.info(SETUP_B)
    assert setup["kind"] == "SETUP" and setup["apo"] == ops.info(ALL_B)["apo"]
    assert setup["regular_channels"] is None and setup["used"] is None
    assert setup["pms_pairs"] is None


def test_memory_file_channel_ops_match_all(tmp_path):
    assert ops.rows(MEMORY_B) == ops.rows(ALL_B)
    out = str(tmp_path / "m.dat")
    ops.set_field(MEMORY_B, 1, "power", "LOW", out)
    assert len(read(out)) == 41472 and load(MemoryImage, out).channels[1].power == "LOW"


def test_apply_specs_empty_on_setup_raises(tmp_path):
    out = tmp_path / "o.dat"
    with pytest.raises(NotInBackup):
        ops.apply_specs(SETUP_B, [], str(out))
    assert not out.exists()


def test_extract_requires_all_and_known_kind(tmp_path):
    out = str(tmp_path / "o.dat")
    with pytest.raises(ValueError, match="MEMORY"):
        ops.extract(MEMORY_B, "setup", out)
    for bad in ("vfo", "all", "ALL", ""):
        with pytest.raises(ValueError, match=f"kind must be memory or setup, got {bad!r}"):
            ops.extract(ALL_B, bad, out)
    assert not os.path.exists(out)
    assert ops.extract(ALL_B, "Memory", out) == out and read(out) == read(MEMORY_B)


def test_merge_checks(tmp_path):
    out = str(tmp_path / "o.dat")
    with pytest.raises(ValueError, match="MEMORY and/or SETUP"):
        ops.merge(ALL_A, out)
    with pytest.raises(ValueError):
        ops.merge(ALL_A, out, memory=SETUP_B)        # wrong kind for --memory
    with pytest.raises(ValueError):
        ops.merge(ALL_A, out, setup=SETUP_B, memory=SETUP_B)
    with pytest.raises(ValueError, match="ALL"):
        ops.merge(SETUP_B, out, memory=MEMORY_B)
    assert not os.path.exists(out)
    assert ops.merge(ALL_A, out, memory=MEMORY_B, setup=SETUP_B) == out
    assert load(CloneImage, out).memory.to_bytes() == read(MEMORY_B)


def test_info_kind_renders_as_plain_string():
    assert '"kind": "SETUP"' in json.dumps(ops.info(SETUP_B))
    assert str(Kind.MEMORY) == "MEMORY" and f"{Kind.ALL}" == "ALL"


def test_memory_backup_csv_round_trip_is_byte_identical(tmp_path):
    csvf, out = tmp_path / "m.csv", tmp_path / "MEMFTM15001.dat"
    ops.export_csv(MEMORY_B, str(csvf))
    ops.import_csv(MEMORY_B, str(csvf), str(out))
    assert out.stat().st_size == 41472
    assert out.read_bytes() == read(MEMORY_B)


def test_apply_specs_on_memory_backup_matches_extract_of_all(tmp_path):
    spec = {"name": "N0CALL", "rx_frequency_mhz": "146.700", "tx_frequency_mhz": "146.100",
            "mode": "FM", "source_id": "XX:42"}
    mem_out, all_out = str(tmp_path / "m.dat"), str(tmp_path / "a.dat")
    mem_ext = str(tmp_path / "e.dat")
    ops.apply_specs(MEMORY_B, [spec], mem_out, start=500)
    ops.apply_specs(ALL_B, [spec], all_out, start=500)
    ops.extract(all_out, "memory", mem_ext)
    got = (tmp_path / "m.dat").read_bytes()
    assert len(got) == 41472
    assert got == (tmp_path / "e.dat").read_bytes()
