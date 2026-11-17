"""No ops write path may change bytes 0x400-0x47F of an ALL image.

The firmware's restore never writes that block (identity/alignment bytes; spec
"PC raw EEPROM command" and docs/firmware-evidence.md), so an edit there would
produce a file whose change silently does nothing on the radio."""
import csv
import shutil

import pytest

from ftm150 import ops
from tests.files import ALL_A, ALL_B, MEMORY_B, SETUP_B, read

IDENT = slice(0x400, 0x480)

# Two valid values for every settable field (README "set" list); the test uses
# the first one that changes the file, so no case is a no-op. tx_mhz needs a
# split channel, so its case sets shift=split first.
SET_CASES = {
    "name": ("TESTNM", "OTHER"),
    "band": ("VHF", "4"),          # 4: an undecoded raw code
    "rx_mhz": ("145.500", "145.525"),
    "tx_mhz": ("146.100", "146.125"),
    "offset_khz": ("600", "1600"),
    "mode": ("AM", "FM"),
    "narrow": ("true", "false"),
    "shift": ("-RPT", "+RPT"),
    "tone_mode": ("TSQL", "TONE"),
    "ctcss_hz": ("88.5", "100.0"),
    "dcs": ("754", "023"),
    "step_khz": ("12.5", "25"),
    "power": ("LOW", "MED"),
    "skip": ("true", "false"),
    "mgrp": ("false", "true"),
    "clock_shift": ("true", "false"),
    "user_ctcss_hz": ("1600", "1700"),
    "enabled": ("true", "false"),
    "show_name": ("true", "false"),
}


def test_set_cases_cover_every_settable_field():
    from ftm150.coerce import SETTABLE
    assert set(SET_CASES) == set(SETTABLE)


@pytest.mark.parametrize("channel", [1, 999])
@pytest.mark.parametrize("field", sorted(SET_CASES))
def test_set_field_keeps_identity(tmp_path, field, channel):
    src = tmp_path / "in.dat"
    shutil.copyfile(ALL_A, src)
    if field == "tx_mhz":
        ops.set_field(str(src), channel, "shift", "split", in_place=True)
    before = read(src)
    for i, value in enumerate(SET_CASES[field]):
        out = tmp_path / f"out{i}.dat"
        ops.set_field(str(src), channel, field, value, str(out))
        after = read(out)
        if after != before:                # the edit did something
            break
    assert after != before, (field, channel)
    assert after[IDENT] == before[IDENT]


def test_import_csv_keeps_identity(tmp_path):
    csv_path = tmp_path / "b.csv"
    ops.export_csv(ALL_B, str(csv_path))
    out = tmp_path / "out.dat"
    ops.import_csv(ALL_A, str(csv_path), str(out))
    assert read(out) != read(ALL_A)
    assert read(out)[IDENT] == read(ALL_A)[IDENT]


def _one_row_csv(path, location, *, chirp):
    """A one-row CSV (native or CHIRP) that puts a 2 m repeater on `location`."""
    row = {"Location": str(location), "Name": "GUARD", "Frequency": "147.000",
           "Duplex": "+", "Offset": "0.600", "Tone": "Tone", "rToneFreq": "91.5",
           "cToneFreq": "91.5", "DtcsCode": "23", "Mode": "FM", "TStep": "5.0",
           "Skip": ""}
    if chirp:
        row.update({"DtcsPolarity": "NN", "Comment": ""})
    else:
        row.update({"Skip": "0", "Band": "VHF", "TxPower": "LOW", "Narrow": "0",
                    "MGrp": "0", "ClockShift": "0", "UserCTCSS": "1500",
                    "ShowName": "1"})
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(row))
        w.writeheader()
        w.writerow(row)


@pytest.mark.parametrize("chirp", [False, True], ids=["native", "chirp"])
@pytest.mark.parametrize("channel", [1, 999], ids=["enabled-ch1", "ch999"])
def test_import_one_row_keeps_identity(tmp_path, chirp, channel):
    """Channel 1 is enabled in ALL_A (the import overwrites it); 999 is the
    last channel, the one nearest the end of the record array."""
    from ftm150 import CloneImage
    from tests.files import load
    assert load(CloneImage, ALL_A).memory.channels[1].enabled
    csv_path = tmp_path / "one.csv"
    _one_row_csv(csv_path, channel, chirp=chirp)
    out = tmp_path / "out.dat"
    ops.import_csv(ALL_A, str(csv_path), str(out), chirp=chirp)
    after = load(CloneImage, str(out)).memory.channels[channel]
    assert after.enabled and after.rx_hz == 147_000_000
    assert read(out)[IDENT] == read(ALL_A)[IDENT]


def _spec(n):
    return {"name": f"RPT{n}", "callsign": f"N0CAL{n}",
            "rx_frequency_mhz": "146.700", "tx_frequency_mhz": "146.100",
            "mode": "FM", "ctcss_tx_hz": "91.5", "ctcss_rx_hz": None,
            "dcs_tx_code": None, "dcs_rx_code": None, "source_id": f"XX:{n}"}


@pytest.mark.parametrize("start", [1, 997])   # 997..999: the last channels
def test_apply_specs_keeps_identity(tmp_path, start):
    out = tmp_path / "out.dat"
    result = ops.apply_specs(ALL_A, [_spec(1), _spec(2), _spec(3)], str(out),
                             start=start)
    assert [a.channel for a in result.applied] == [start, start + 1, start + 2]
    assert read(out)[IDENT] == read(ALL_A)[IDENT]


@pytest.mark.parametrize("parts", [
    {"memory": MEMORY_B}, {"setup": SETUP_B},
    {"memory": MEMORY_B, "setup": SETUP_B}], ids=["memory", "setup", "both"])
def test_merge_keeps_identity(tmp_path, parts):
    """MEMORY and SETUP files do not carry 0x400-0x47F, so this guards against a
    merge_ranges bug that would map partial bytes onto that block. The base's
    block is marked first, so any such write shows up."""
    base = tmp_path / "base.dat"
    data = bytearray(read(ALL_A))
    data[IDENT] = bytes(b ^ 0x5A for b in data[IDENT])
    base.write_bytes(bytes(data))
    out = tmp_path / "out.dat"
    ops.merge(str(base), str(out), **parts)
    assert read(out) != bytes(data)
    assert read(out)[IDENT] == bytes(data)[IDENT]
