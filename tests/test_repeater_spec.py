import pytest

from ftm150.engine.tables import Band
from ftm150.interop import repeater_spec as rs


def test_derive_band_2m_is_vhf():
    assert rs.derive_band(146_700_000) is Band.VHF


def test_derive_band_70cm_is_uhf():
    assert rs.derive_band(438_000_000) is Band.UHF


def test_derive_band_out_of_range_raises():
    with pytest.raises(rs.UnrepresentableError):
        rs.derive_band(27_000_000)


def test_shift_simplex():
    assert rs.derive_shift_offset(146_500_000, 146_500_000) == ("simplex", None, None)


def test_shift_minus_rpt_600khz():
    assert rs.derive_shift_offset(146_700_000, 146_100_000) == ("-RPT", 600_000, None)


def test_shift_plus_rpt_5mhz():
    assert rs.derive_shift_offset(438_000_000, 443_000_000) == ("+RPT", 5_000_000, None)


def test_shift_split_on_non_50khz_offset():
    # 12.5 kHz offset isn't a multiple of 50 -> store absolute tx
    assert rs.derive_shift_offset(146_500_000, 146_512_500) == ("split", None, 146_512_500)


def test_tone_off():
    assert rs.derive_tone(None, None, None) == ("OFF", {}, [])


def test_tone_tone_tx_only():
    assert rs.derive_tone("91.5", None, None) == ("TONE", {"ctcss_hz": 91.5}, [])


def test_tone_tsql_equal():
    assert rs.derive_tone("91.5", "91.5", None) == ("TSQL", {"ctcss_hz": 91.5}, [])


def test_tone_differing_tx_rx_uses_tx_with_note():
    mode, fields, notes = rs.derive_tone("91.5", "88.5", None)
    assert mode == "TONE"
    assert fields == {"ctcss_hz": 91.5}
    assert notes and "88.5" in notes[0]


def test_tone_dcs_same_code_both_ways():
    assert rs.derive_tone(None, None, "023", "023") == ("DCS", {"dcs": 23}, [])


def test_tone_dcs_tx_only_applies_with_note():
    # FTM-150 has one DCS mode (encode+decode); no confirmed encode-only mode.
    mode, fields, notes = rs.derive_tone(None, None, "D023N", None)
    assert (mode, fields) == ("DCS", {"dcs": 23})
    assert notes and "023" in notes[0]


def test_tone_dcs_rx_only_applies_with_note():
    mode, fields, notes = rs.derive_tone(None, None, None, "023")
    assert (mode, fields) == ("DCS", {"dcs": 23})
    assert notes


def test_tone_dcs_differing_codes_raises():
    with pytest.raises(rs.UnrepresentableError):
        rs.derive_tone(None, None, "023", "025")


def test_tone_dcs_beats_ctcss_with_note():
    mode, fields, notes = rs.derive_tone("91.5", None, "023", "023")
    assert (mode, fields) == ("DCS", {"dcs": 23})
    assert notes and "91.5" in notes[0]


def test_spec_to_fields_reads_producer_dcs_fields():
    fields, _ = rs.spec_to_fields(_spec(ctcss_tx_hz=None,
                                        dcs_tx_code="023", dcs_rx_code="023"))
    assert fields["tone_mode"] == "DCS" and fields["dcs"] == 23


def test_spec_to_fields_accepts_legacy_dcs_code():
    fields, _ = rs.spec_to_fields(_spec(ctcss_tx_hz=None, dcs_code="023"))
    assert fields["tone_mode"] == "DCS" and fields["dcs"] == 23


def test_tone_non_standard_ctcss_raises():
    with pytest.raises(rs.UnrepresentableError):
        rs.derive_tone("67.1", None, None)


def _spec(**over):
    base = {
        "name": "N0CALL", "callsign": "N0CALL",
        "rx_frequency_mhz": "146.700", "tx_frequency_mhz": "146.100",
        "mode": "FM", "ctcss_tx_hz": "91.5", "ctcss_rx_hz": None,
        "dcs_tx_code": None, "dcs_rx_code": None, "source_id": "XX:42",
    }
    base.update(over)
    return base


def test_sanitize_name_truncates_and_strips():
    name, notes = rs.sanitize_name({"name": "N0CALL-Example Hill ❤", "callsign": None})
    assert len(name) <= 8
    assert all(ord(c) < 128 for c in name)
    assert notes


def test_spec_to_fields_fm_repeater():
    fields, _notes = rs.spec_to_fields(_spec())
    assert fields["band"] is Band.VHF
    assert fields["rx_hz"] == 146_700_000
    assert fields["shift"] == "-RPT"
    assert fields["offset_hz"] == 600_000
    assert fields["mode"] == "FM"
    assert fields["tone_mode"] == "TONE"
    assert fields["ctcss_hz"] == 91.5
    assert fields["name"] == "N0CALL"


def test_spec_to_fields_digital_mode_raises():
    with pytest.raises(rs.UnrepresentableError):
        rs.spec_to_fields(_spec(mode="DMR"))


def test_spec_to_fields_split_sets_tx():
    # 25 kHz offset: on the 5 kHz grid but not a 50 kHz multiple -> split.
    fields, _ = rs.spec_to_fields(_spec(rx_frequency_mhz="146.5000",
                                        tx_frequency_mhz="146.5250"))
    assert fields["shift"] == "split"
    assert fields["tx_hz"] == 146_525_000
    assert "offset_hz" not in fields


def test_spec_to_fields_missing_mode_raises():
    spec = _spec()
    del spec["mode"]
    with pytest.raises(rs.UnrepresentableError):
        rs.spec_to_fields(spec)


def test_tone_rx_only_notes_applied_as_tx():
    mode, fields, notes = rs.derive_tone(None, "91.5", None)
    assert mode == "TONE"
    assert fields == {"ctcss_hz": 91.5}
    assert notes and "91.5" in notes[0] and "rx-only" in notes[0]


# --- edge cases admitted by the upstream schema ---

def test_tone_dcs_normal_polarity_suffix_accepted():
    assert rs.derive_tone(None, None, "023N", "023n")[:2] == ("DCS", {"dcs": 23})


def test_tone_dcs_inverted_polarity_refused():
    # FTM-150 DCS polarity storage is not decoded; never write inverted as normal.
    with pytest.raises(rs.UnrepresentableError, match="polarity"):
        rs.derive_tone(None, None, "023I", "023I")
    with pytest.raises(rs.UnrepresentableError, match="polarity"):
        rs.derive_tone(None, None, "023N", "023I")


def test_tone_dcs_garbage_refused():
    with pytest.raises(rs.UnrepresentableError):
        rs.derive_tone(None, None, "0X23", None)


@pytest.mark.parametrize("rx", ["146.700500", "146.706250", "146.701250", "146.7001"])
def test_spec_to_fields_refuses_off_grid_rx(rx):
    with pytest.raises(rs.UnrepresentableError, match=r"2\.5 kHz"):
        rs.spec_to_fields(_spec(rx_frequency_mhz=rx))


def test_spec_to_fields_refuses_off_grid_split_tx():
    with pytest.raises(rs.UnrepresentableError, match=r"2\.5 kHz"):
        rs.spec_to_fields(_spec(rx_frequency_mhz="438.000",
                                tx_frequency_mhz="430.40625"))


@pytest.mark.parametrize("rx, hz", [("+146.7", 146_700_000), ("0146.700", 146_700_000),
                                    ("146.705000", 146_705_000)])
def test_spec_to_fields_accepts_schema_number_forms(rx, hz):
    fields, _ = rs.spec_to_fields(_spec(rx_frequency_mhz=rx,
                                        tx_frequency_mhz="146.100"))
    assert fields["rx_hz"] == hz


def test_spec_to_fields_accepts_2k5_grid():
    # UHF CB repeater CH41 (12.5 kHz plan): rx 476.4375, tx 477.1875
    fields, _ = rs.spec_to_fields(_spec(rx_frequency_mhz="476.4375",
                                        tx_frequency_mhz="477.1875"))
    assert (fields["rx_hz"], fields["shift"], fields["offset_hz"]) == (
        476_437_500, "+RPT", 750_000)
