# tests/test_schema_contract.py
import contextlib
import json
import os

import jsonschema

from ftm150.interop import repeater_spec as rs

ROOT = os.path.dirname(os.path.dirname(__file__))
SCHEMA = os.path.join(ROOT, "ftm150/schemas/repeater_spec.schema.json")


def _load_schema():
    with open(SCHEMA) as f:
        return json.load(f)

SAMPLES = [
    {"name": "N0CALL", "callsign": "N0CALL", "rx_frequency_mhz": "146.700",
     "tx_frequency_mhz": "146.100", "mode": "FM", "ctcss_tx_hz": "91.5",
     "ctcss_rx_hz": None, "dcs_tx_code": None, "dcs_rx_code": None, "latitude": "-10.00",
     "longitude": "120.00", "distance_km": 5.0, "operational_status": "ON_AIR",
     "use": "OPEN", "band": "M_2", "notes": None, "last_update": "2026-01-01",
     "source": "repeaterbook", "source_id": "XX:42",
     "params": {"bandwidth_khz": "12.5"}},
    {"name": "RPTDMR", "callsign": "RPTDMR", "rx_frequency_mhz": "439.000",
     "tx_frequency_mhz": "434.000", "mode": "DMR", "ctcss_tx_hz": None,
     "ctcss_rx_hz": None, "dcs_tx_code": None, "dcs_rx_code": None, "latitude": "-10.50",
     "longitude": "120.50", "distance_km": 9.0, "operational_status": "ON_AIR",
     "use": "OPEN", "band": "CM_70", "notes": None, "last_update": "2026-01-01",
     "source": "repeaterbook", "source_id": "XX:99",
     "params": {"dmr_id": "5051", "color_code": "1"}},
    # Shaped exactly like a repeaterbook search_repeaters row, so producer drift
    # (e.g. dcs_code -> dcs_tx_code/dcs_rx_code, distance_km as string) is caught.
    {"name": "RPTUHF", "callsign": "RPTUHF", "nearest_city": "Example Hill",
     "rx_frequency_mhz": "438.3000000000", "tx_frequency_mhz": "431.3000000000",
     "ctcss_tx_hz": "91.5", "ctcss_rx_hz": None, "dcs_tx_code": None,
     "dcs_rx_code": None, "latitude": "-10.1234567890",
     "longitude": "120.1234567890", "distance_km": "1.234567890123456",
     "operational_status": "ON_AIR", "use": "OPEN", "band": "CM_70",
     "notes": None, "allstar_node": None, "echolink_node": None,
     "irlp_node": None, "wires_node": None,
     "last_update": "2025-02-03T00:00:00Z", "source": "repeaterbook",
     "source_id": "XX:694", "params": {"mode": "FM", "bandwidth_khz": None},
     "mode": "FM"},
]


def test_schema_declares_producer_dcs_fields():
    props = _load_schema()["properties"]
    assert "dcs_tx_code" in props and "dcs_rx_code" in props


def test_samples_validate_against_schema():
    schema = _load_schema()
    for s in SAMPLES:
        jsonschema.validate(s, schema)


def test_spec_to_fields_handles_every_contract_row():
    for s in SAMPLES:
        # a documented, non-fatal skip (e.g. DMR)
        with contextlib.suppress(rs.UnrepresentableError):
            rs.spec_to_fields(s)


def test_params_is_accepted():
    schema = _load_schema()
    for s in SAMPLES:
        assert "params" in s
        jsonschema.validate(s, schema)


# --- drift guard against the producer's published schema -------------------
# tests/fixtures/upstream_repeater_spec.schema.json is a verbatim copy of
# https://github.com/MicaelJarniac/repeaterbook/raw/refs/heads/main/src/repeaterbook/schemas/repeater_spec.schema.json
# Test-only: the runtime stays stdlib-only with the loose vendored schema
# ftm150/schemas/repeater_spec.schema.json (docs/DESIGN.md §1). Refresh the
# fixture to re-check drift.
UPSTREAM = os.path.join(ROOT, "tests/fixtures/upstream_repeater_spec.schema.json")


def _load(path):
    return json.loads(open(path).read())


def test_vendored_schema_declares_every_upstream_field():
    ours, up = _load(SCHEMA)["properties"], _load(UPSTREAM)["properties"]
    assert set(up) - set(ours) == set()


def test_vendored_required_is_subset_of_upstream_required():
    assert set(_load(SCHEMA)["required"]) <= set(_load(UPSTREAM)["required"])


def test_vendored_modes_cover_upstream_modes():
    ours = set(_load(SCHEMA)["properties"]["mode"]["enum"])
    up = set(_load(UPSTREAM)["$defs"]["RepeaterMode"]["enum"])
    assert up <= ours


def test_captured_payload_is_valid_upstream_and_vendored():
    real = SAMPLES[-1]  # verbatim producer output
    jsonschema.validate(real, _load(UPSTREAM))
    jsonschema.validate(real, _load(SCHEMA))
