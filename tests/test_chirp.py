# tests/test_chirp.py
import dataclasses
import typing

import pytest

from ftm150 import chirp, csv_io
from ftm150.engine.record import ChannelRecord, write_record
from ftm150.engine.tables import Band, RawCode
from ftm150.interop import repeater_spec

# CH1 as a record: RPT2M-A, 146.900 MHz, -RPT 0.600 MHz, TONE 123.0, FM, MED.
NATIVE = ChannelRecord(
    enabled=True, name="RPT2M-A", band=Band.VHF, rx_hz=146_900_000, shift="-RPT",
    offset_hz=600_000, tx_hz=None, mode="FM", narrow=False, tone_mode="TONE",
    ctcss_hz=123.0, dcs=23, step=25.0, power="MED", skip=False, mgrp=False,
    clock_shift=False, user_ctcss_hz=1500, show_name=True,
)


@pytest.mark.parametrize("td", [chirp.ChirpFields, chirp.ChirpDefaults,
                                repeater_spec.SpecFields, repeater_spec.ToneFields])
def test_field_typeddicts_match_channelrecord(td):
    """Each interop field TypedDict names only ChannelRecord fields, with
    ChannelRecord's value types, so the two cannot drift."""
    record_types = typing.get_type_hints(ChannelRecord)
    assert {f.name for f in dataclasses.fields(ChannelRecord)} == set(record_types)
    hints = typing.get_type_hints(td)
    assert set(hints) <= set(record_types)
    for key, hint in hints.items():
        assert hint == record_types[key], key


_SIMPLEX_SPEC = {"name": "SIMPLEX", "mode": "FM",
                 "rx_frequency_mhz": "146.500", "tx_frequency_mhz": "146.500"}


def test_field_typeddicts_cover_what_the_code_produces():
    """The drift test above only catches extra keys; these catch a key dropped
    from a TypedDict (required keys == what is always produced, optional
    keys the code can emit are all declared)."""
    assert chirp.ChirpFields.__required_keys__ == set(chirp.chirp_to_fields(UHF)[1])
    assert chirp.ChirpDefaults.__required_keys__ == set(chirp.CHIRP_DEFAULTS)

    simplex = repeater_spec.spec_to_fields(_SIMPLEX_SPEC)[0]
    assert repeater_spec.SpecFields.__required_keys__ == set(simplex)
    declared = set(typing.get_type_hints(repeater_spec.SpecFields))
    split = repeater_spec.spec_to_fields({**_SIMPLEX_SPEC, "tx_frequency_mhz": "146.100"})[0]
    split_tx = repeater_spec.spec_to_fields({**_SIMPLEX_SPEC, "tx_frequency_mhz": "146.520"})[0]
    ctcss = repeater_spec.spec_to_fields({**_SIMPLEX_SPEC, "ctcss_tx_hz": "91.5"})[0]
    dcs = repeater_spec.spec_to_fields({**_SIMPLEX_SPEC, "dcs_tx_code": "023"})[0]
    produced = set(split) | set(split_tx) | set(ctcss) | set(dcs)
    assert {"offset_hz", "tx_hz", "ctcss_hz", "dcs"} <= produced   # all optionals exercised
    assert produced <= declared

    tone_declared = set(typing.get_type_hints(repeater_spec.ToneFields))
    tone_keys: set[str] = set()
    for args in [("91.5", None, None), (None, None, "023")]:
        tone_keys |= set(repeater_spec.derive_tone(*args)[1])
    assert tone_keys == {"ctcss_hz", "dcs"}
    assert tone_keys <= tone_declared


def test_record_to_chirp_keeps_shared_fields():
    row = chirp.record_to_chirp(1, NATIVE)
    assert row["Location"] == "1"
    assert row["Name"] == "RPT2M-A"
    assert row["Frequency"] == "146.9"
    assert row["Duplex"] == "-"
    assert row["Offset"] == "0.600"
    assert row["Tone"] == "Tone"
    assert (row["rToneFreq"], row["cToneFreq"], row["DtcsCode"]) == ("123.0", "123.0", "23")
    assert (row["Mode"], row["TStep"], row["DtcsPolarity"]) == ("FM", "25.0", "NN")
    assert list(row) == chirp.CHIRP_COLUMNS
    assert set(chirp.CHIRP_COLUMNS).isdisjoint({"Band", "TxPower", "UserCTCSS"})


def test_record_to_chirp_does_not_use_native_rows(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("CHIRP export went through a native CSV row")
    monkeypatch.setattr(csv_io, "record_to_row", boom)
    assert chirp.record_to_chirp(1, NATIVE)["Name"] == "RPT2M-A"


def test_record_to_chirp_narrow_is_nfm_and_split_offset_is_tx():
    rec = dataclasses.replace(NATIVE, narrow=True, shift="split", offset_hz=None,
                              tx_hz=147_250_000)
    row = chirp.record_to_chirp(1, rec)
    assert (row["Mode"], row["Duplex"], row["Offset"]) == ("NFM", "split", "147.25")


def test_native_chirp_native_preserves_shared_fields(blank):
    n, f = chirp.chirp_to_fields(chirp.record_to_chirp(1, NATIVE))
    assert n == 1
    for k in ("name", "band", "rx_hz", "shift", "offset_hz", "tx_hz", "mode",
              "narrow", "tone_mode", "ctcss_hz", "step", "skip"):
        assert f[k] == getattr(NATIVE, k), k
    assert type(f["band"]) is Band
    img, _ = blank
    ch = img.memory.channels[1]
    write_record(ch, dataclasses.replace(ch.to_record(), enabled=True,
                                         **chirp.CHIRP_DEFAULTS, **f))
    assert ch.band == Band.VHF and ch.rx_hz == 146_900_000


UHF = {"Location": "5", "Name": "RPT UHF", "Frequency": "438.025000", "Duplex": "-",
       "Offset": "7.000000", "Tone": "Tone", "rToneFreq": "91.5", "cToneFreq": "88.5",
       "DtcsCode": "023", "DtcsPolarity": "NN", "Mode": "FM", "TStep": "5.00",
       "Skip": "", "Comment": ""}
VHF = {**UHF, "Location": "6", "Name": "SIMPLEX", "Frequency": "146.500000", "Duplex": "",
       "Offset": "0.000000", "Tone": "", "Mode": "NFM", "TStep": "12.50", "Skip": "S"}


def test_chirp_to_fields_pure():
    n, f = chirp.chirp_to_fields(UHF)
    assert n == 5 and f["band"] == Band.UHF and f["rx_hz"] == 438_025_000 and "power" not in f


def test_chirp_to_fields_real_rows_apply(blank):
    img, _ = blank
    for row in (UHF, VHF):
        n, f = chirp.chirp_to_fields(row)
        ch = img.memory.channels[n]
        write_record(ch, dataclasses.replace(ch.to_record(), enabled=True,
                                             **chirp.CHIRP_DEFAULTS, **f))
    u, v = img.memory.channels[5], img.memory.channels[6]
    assert (u.band, u.rx_hz, u.shift, u.offset_hz, u.ctcss_hz) == (
        Band.UHF, 438_025_000, "-RPT", 7_000_000, 91.5)
    assert (v.band, v.narrow, v.mode, v.skip, v.step_khz) == (Band.VHF, True, "FM", True, 12.5)
    assert (u.power, u.mgrp, u.clock_shift, u.user_ctcss_hz) == ("HIGH", False, False, 1500)


def test_chirp_to_fields_rejects_inverted_dcs():
    with pytest.raises(ValueError):
        chirp.chirp_to_fields({**UHF, "DtcsPolarity": "RN"})


def test_chirp_to_fields_tsql_uses_ctone_and_dtcs_code():
    _, t = chirp.chirp_to_fields({**UHF, "Tone": "TSQL"})
    assert (t["tone_mode"], t["ctcss_hz"], t["dcs"]) == ("TSQL", 88.5, None)
    _, d = chirp.chirp_to_fields({**UHF, "Tone": "DTCS"})
    assert (d["tone_mode"], d["dcs"], d["ctcss_hz"]) == ("DCS", 23, None)
    _, o = chirp.chirp_to_fields(VHF)
    assert (o["tone_mode"], o["ctcss_hz"], o["dcs"]) == ("OFF", None, None)


def test_chirp_to_fields_maps_fields_and_defaults():
    (nu, u), (nv, v) = chirp.chirp_to_fields(UHF), chirp.chirp_to_fields(VHF)
    assert (u["band"], u["skip"], u["narrow"], u["mode"]) == (Band.UHF, False, False, "FM")
    assert (v["band"], v["skip"], v["narrow"], v["mode"]) == (Band.VHF, True, True, "FM")
    assert (nu, nv) == (5, 6)
    assert (u["shift"], u["offset_hz"], u["tx_hz"]) == ("-RPT", 7_000_000, None)
    assert chirp.CHIRP_DEFAULTS == {"power": "HIGH", "mgrp": False, "clock_shift": False,
                                    "user_ctcss_hz": 1500}
    for k in (*chirp.CHIRP_DEFAULTS, "show_name", "enabled"):
        assert k not in u, k
    assert set(u) <= {f.name for f in dataclasses.fields(ChannelRecord)}
    _, am = chirp.chirp_to_fields({**UHF, "Mode": "AM", "Frequency": "125.0"})
    assert am["mode"] == "AM"


def test_chirp_to_fields_split_carries_tx_not_offset():
    _, f = chirp.chirp_to_fields({**UHF, "Duplex": "split", "Offset": "430.025000"})
    assert (f["shift"], f["tx_hz"], f["offset_hz"]) == ("split", 430_025_000, None)


def test_chirp_to_fields_errors_are_valueerror():
    for bad in ({"Skip": "X"}, {"Frequency": "50.0"}, {"Mode": "DIG"}):
        with pytest.raises(ValueError):
            chirp.chirp_to_fields({**UHF, **bad})


@pytest.mark.parametrize("bad", [{"Duplex": "x"}, {"Duplex": "5"}, {"Tone": "Cross"},
                                 {"Tone": "3"}])
def test_chirp_to_fields_validates_duplex_and_tone_early(bad):
    with pytest.raises(ValueError, match="CH5"):
        chirp.chirp_to_fields({**UHF, **bad})


@pytest.mark.parametrize("raw", [{"shift": RawCode(5)}, {"tone_mode": RawCode(3)},
                                 {"band": RawCode(6)}, {"power": RawCode(3)},
                                 {"step": RawCode(12)}])
def test_record_to_chirp_refuses_raw_codes(raw):
    with pytest.raises(ValueError, match="CH1"):
        chirp.record_to_chirp(1, dataclasses.replace(NATIVE, **raw))


def test_record_to_chirp_refuses_raw_codes_from_image(blank):
    img, ch = blank
    ch.band = Band.VHF
    ch.rx_hz = 146_500_000
    ch.enabled = True
    img._buf[0x801] = (img._buf[0x801] & ~0x07) | 5
    with pytest.raises(ValueError):
        chirp.record_to_chirp(1, ch.to_record())


@pytest.mark.parametrize("tone, col", [("Tone", "rToneFreq"), ("TSQL", "cToneFreq"),
                                       ("DTCS", "DtcsCode")])
@pytest.mark.parametrize("missing", ["blank", "absent"])
def test_chirp_to_fields_tone_mode_needs_its_value_column(tone, col, missing):
    row = {**UHF, "Tone": tone}
    if missing == "blank":
        row[col] = "  "
    else:
        del row[col]
    with pytest.raises(ValueError, match=f"CH5: Tone mode '{tone}' needs {col}"):
        chirp.chirp_to_fields(row)


def test_record_to_chirp_writes_skip():
    assert chirp.record_to_chirp(1, dataclasses.replace(NATIVE, skip=True))["Skip"] == "S"
    assert chirp.record_to_chirp(1, NATIVE)["Skip"] == ""
    _, f = chirp.chirp_to_fields(chirp.record_to_chirp(1, dataclasses.replace(NATIVE, skip=True)))
    assert f["skip"] is True


@pytest.mark.parametrize("bad, col", [({"Mode": "DV"}, "Mode"), ({"Mode": "WFM"}, "Mode"),
                                      ({"Duplex": "off"}, "Duplex"),
                                      ({"Tone": "Cross"}, "Tone")])
def test_chirp_to_fields_refuses_unsupported_values_with_ch_prefix(bad, col):
    with pytest.raises(ValueError, match=f"^CH5: {col} "):
        chirp.chirp_to_fields({**UHF, **bad})


def test_chirp_to_fields_tone_off_with_blank_value_columns_carries_no_tone():
    _, f = chirp.chirp_to_fields({**UHF, "Tone": "", "rToneFreq": "", "cToneFreq": "",
                                  "DtcsCode": ""})
    assert (f["tone_mode"], f["ctcss_hz"], f["dcs"]) == ("OFF", None, None)
