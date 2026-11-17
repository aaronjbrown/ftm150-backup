import dataclasses
import itertools

import pytest

from ftm150 import CloneImage, ops
from ftm150.engine import layout
from ftm150.engine.tables import Band
from ftm150.interop import repeater_spec as rs
from ftm150.ops import save_image
from tests.files import ALL_A, ALL_B, load


def _spec(**over):
    base = {"name": "N0CALL", "callsign": "N0CALL",
            "rx_frequency_mhz": "146.700", "tx_frequency_mhz": "146.100",
            "mode": "FM", "ctcss_tx_hz": "91.5", "ctcss_rx_hz": None,
            "dcs_tx_code": None, "dcs_rx_code": None, "source_id": "XX:42"}
    base.update(over)
    return base


_OPTIONAL = ("offset_hz", "tx_hz", "ctcss_hz", "dcs")   # None = not carried
_ENUMS = ("band", "shift", "tone_mode", "power", "step")


_OUT_SEQ = itertools.count()   # unique OUT name per _apply call


def _apply(tmp_path, specs, start, base=ALL_A):
    """ops.apply_specs onto a fresh OUT; return (result, the saved OUT image)."""
    out = str(tmp_path / f"out{next(_OUT_SEQ)}.dat")
    result = ops.apply_specs(base, specs, out, start=start)
    return result, load(CloneImage, out)


def _assert_matches_spec(img, n, spec):
    """CH n's record is exactly what spec_to_record says, apart from the
    optional fields the spec does not carry (those keep the target's bits)."""
    got = img.memory.channels[n].to_record()
    want, _ = rs.spec_to_record(spec, user_ctcss_hz=got.user_ctcss_hz)
    want = dataclasses.replace(want, **{f: getattr(got, f) for f in _OPTIONAL
                                        if getattr(want, f) is None})
    assert got == want, n
    for f in _ENUMS:
        assert type(getattr(got, f)) is type(getattr(want, f)), (n, f)


def test_apply_writes_fm_skips_digital(tmp_path):
    result, img = _apply(
        tmp_path,
        [_spec(), _spec(mode="DMR", source_id="XX:99", name="RPTDMR")],
        start=200,
    )
    assert len(result.applied) == 1
    assert result.applied[0].channel == 200
    assert len(result.skipped) == 1
    assert result.skipped[0].source_id == "XX:99"
    assert "FM-only" in result.skipped[0].reason
    ch = img.memory.channels[200]
    assert ch.enabled and ch.rx_hz == 146_700_000 and ch.ctcss_hz == 91.5
    _assert_matches_spec(img, 200, _spec())


def test_apply_is_local(tmp_path):
    """Only the written channel changes; other enabled channels are byte-identical."""
    before = load(CloneImage, ALL_A)
    _, img = _apply(tmp_path, [_spec()], start=200)
    for n in range(1, layout.NUM_REGULAR + 1):
        if n == 200:
            continue
        if before.memory.channels[n].enabled:
            assert before.memory.channels[n].raw == img.memory.channels[n].raw, n


def test_apply_start_out_of_range_raises(tmp_path):
    with pytest.raises(ValueError):
        _apply(tmp_path, [_spec()], start=0)


def test_apply_resets_stale_bits_on_previously_dirtied_empty_channel(tmp_path):
    """A disabled channel can still carry stale narrow/power/etc bits from a
    prior edit; apply_specs must reset them to deterministic defaults rather
    than inheriting whatever was left over."""
    dirty = load(CloneImage, ALL_A)
    assert not dirty.memory.channels[200].enabled
    dirty.memory.channels[200].narrow = True
    dirty.memory.channels[200].power = "LOW"
    base = str(tmp_path / "dirty.dat")
    save_image(dirty, base)
    _, img = _apply(tmp_path, [_spec()], start=200, base=base)
    assert img.memory.channels[200].narrow is False
    assert img.memory.channels[200].power == "HIGH"
    _assert_matches_spec(img, 200, _spec())


def test_narrow_bandwidth_sets_narrow_true():
    fields, _ = rs.spec_to_fields(_spec(params={"bandwidth_khz": "12.5"}))
    assert fields["narrow"] is True


def test_wide_bandwidth_sets_narrow_false():
    fields, _ = rs.spec_to_fields(_spec(params={"bandwidth_khz": "25.0"}))
    assert fields["narrow"] is False


def test_absent_bandwidth_defaults_wide():
    fields, _ = rs.spec_to_fields(_spec(params={}))
    assert fields["narrow"] is False


def test_missing_params_defaults_wide():
    fields, _ = rs.spec_to_fields(_spec())
    assert fields["narrow"] is False


def test_apply_programs_narrow_from_bandwidth(tmp_path):
    _, img = _apply(tmp_path, [_spec(params={"bandwidth_khz": "12.5"})], start=200)
    assert img.memory.channels[200].narrow is True
    _assert_matches_spec(img, 200, _spec(params={"bandwidth_khz": "12.5"}))


def test_apply_notes_overwrite_of_occupied_channel(tmp_path):
    assert load(CloneImage, ALL_A).memory.channels[1].enabled
    result, img = _apply(tmp_path, [_spec()], start=1)
    assert len(result.applied) == 1
    notes = result.applied[0].notes
    assert any("overwrote" in n and "1" in n for n in notes)
    _assert_matches_spec(img, 1, _spec())


def test_apply_specs_sets_name_display(tmp_path):
    # User preference: generated channels display their name.
    base = ALL_B
    spec = {"name": "N0CALL", "callsign": "N0CALL", "rx_frequency_mhz": "147.125",
            "tx_frequency_mhz": "146.525", "mode": "FM", "ctcss_tx_hz": "91.5",
            "ctcss_rx_hz": None, "dcs_tx_code": None, "dcs_rx_code": None,
            "source_id": "XX:583"}
    res, img = _apply(tmp_path, [spec], start=500, base=base)
    assert not res.skipped
    assert img.memory.channels[500].show_name is True
    _assert_matches_spec(img, 500, spec)


def test_apply_reports_cross_band_split_and_applies_rest(tmp_path):
    result, img = _apply(
        tmp_path,
        [_spec(tx_frequency_mhz="440.000", source_id="X:1"),
         _spec(source_id="X:2")],
        start=200,
    )
    assert [a.channel for a in result.applied] == [200]
    assert [s.source_id for s in result.skipped] == ["X:1"]
    assert "outside band" in result.skipped[0].reason
    _assert_matches_spec(img, 200, _spec(source_id="X:2"))


def test_apply_rebands_occupied_channel(tmp_path):
    first = str(tmp_path / "first.dat")
    ops.apply_specs(ALL_A, [_spec(rx_frequency_mhz="438.025", tx_frequency_mhz="430.025")],
                    first, start=200)
    result, img = _apply(tmp_path, [_spec()], start=200, base=first)
    assert len(result.applied) == 1 and img.memory.channels[200].rx_hz == 146_700_000
    _assert_matches_spec(img, 200, _spec())


def test_apply_in_band_large_offset_is_split(tmp_path):
    """A >12.75 MHz offset cannot be stored as +/-RPT: in-band, it is a split."""
    spec = _spec(rx_frequency_mhz="438.025", tx_frequency_mhz="420.000")
    result, img = _apply(tmp_path, [spec], start=200)
    assert [a.shift for a in result.applied] == ["split"] and not result.skipped
    ch = img.memory.channels[200]
    assert (ch.band, ch.shift, ch.rx_hz, ch.tx_hz) == (Band.UHF, "split", 438_025_000,
                                                       420_000_000)
    _assert_matches_spec(img, 200, spec)


def test_spec_to_record_is_pure_and_sets_policy():
    rec, notes = rs.spec_to_record(_spec(), user_ctcss_hz=1200)
    assert (rec.enabled, rec.name, rec.band, rec.rx_hz, rec.shift, rec.offset_hz,
            rec.tx_hz) == (True, "N0CALL", Band.VHF, 146_700_000, "-RPT", 600_000, None)
    assert (rec.mode, rec.narrow, rec.tone_mode, rec.ctcss_hz, rec.dcs) == (
        "FM", False, "TONE", 91.5, None)
    assert (rec.power, rec.step, rec.skip, rec.mgrp, rec.clock_shift, rec.show_name,
            rec.user_ctcss_hz) == ("HIGH", 5.0, False, False, False, True, 1200)
    assert notes == []


def test_spec_to_record_split_and_simplex_leave_offset_uncarried():
    split, _ = rs.spec_to_record(_spec(rx_frequency_mhz="146.5000",
                                       tx_frequency_mhz="146.5250"), user_ctcss_hz=1500)
    assert (split.shift, split.tx_hz, split.offset_hz) == ("split", 146_525_000, None)
    simplex, _ = rs.spec_to_record(_spec(tx_frequency_mhz="146.700"), user_ctcss_hz=1500)
    assert (simplex.shift, simplex.tx_hz, simplex.offset_hz) == ("simplex", None, None)


def test_spec_to_record_refuses_cross_band_split():
    with pytest.raises(rs.UnrepresentableError, match="outside band"):
        rs.spec_to_record(_spec(tx_frequency_mhz="440.000"), user_ctcss_hz=1500)


@pytest.mark.parametrize("specs", [{"name": "x"}, [1], [None, {}], "abc"])
def test_apply_specs_requires_list_of_mappings(tmp_path, specs):
    out = tmp_path / "o.dat"
    with pytest.raises(ValueError, match="specs must be a JSON list of objects"):
        ops.apply_specs(ALL_A, specs, str(out))
    assert not out.exists()


@pytest.mark.parametrize(("over", "reason"), [
    ({"name": 123}, "name: expected a string, got int"),
    ({"name": None, "callsign": 7}, "callsign: expected a string, got int"),
    ({"mode": ["FM"]}, "mode: expected a string, got list"),
    ({"ctcss_tx_hz": [1]}, "ctcss_tx_hz: not a tone frequency: [1]"),
    ({"ctcss_rx_hz": "abc"}, "ctcss_rx_hz: not a tone frequency: 'abc'"),
    ({"params": [12.5]}, "params: expected an object, got list"),
    ({"tx_frequency_mhz": None}, "missing tx_frequency_mhz"),
])
def test_spec_to_record_wrong_type_is_unrepresentable(over, reason):
    with pytest.raises(rs.UnrepresentableError) as ei:
        rs.spec_to_record(_spec(**over), user_ctcss_hz=1500)
    assert str(ei.value) == reason


def test_apply_specs_skips_malformed_rows_and_applies_rest(tmp_path):
    res, img = _apply(tmp_path, [_spec(name=123, source_id="bad"), _spec()], 200)
    assert [s.source_id for s in res.skipped] == ["bad"]
    assert [a.channel for a in res.applied] == [200]
    assert img.memory.channels[200].name == "N0CALL"


def test_apply_specs_cuts_a_long_callsign_to_8(tmp_path):
    result, img = _apply(tmp_path, [_spec(name=None, callsign="LONGCALLSIGN")], start=1)
    assert img.memory.channels[1].name == "LONGCALL"
    assert any("adjusted" in n for n in result.applied[0].notes)


def test_apply_specs_cuts_a_long_name_to_8(tmp_path):
    result, img = _apply(tmp_path, [_spec(name="LONGNAME-X")], start=1)
    assert img.memory.channels[1].name == "LONGNAME"
    assert any("adjusted" in n for n in result.applied[0].notes)
