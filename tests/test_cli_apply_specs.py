import json

import pytest

from ftm150 import CloneImage, cli
from tests.files import ALL_A, load

SPECS = [
    {"name": "N0CALL", "callsign": "N0CALL", "rx_frequency_mhz": "146.700",
     "tx_frequency_mhz": "146.100", "mode": "FM", "ctcss_tx_hz": "91.5",
     "ctcss_rx_hz": None, "dcs_code": None, "source_id": "XX:42"},
    {"name": "RPTDMR", "mode": "DMR", "rx_frequency_mhz": "439.000",
     "tx_frequency_mhz": "434.000", "source_id": "XX:99"},
]


def test_apply_specs_json(tmp_path, capsys):
    specs = tmp_path / "specs.json"
    specs.write_text(json.dumps(SPECS))
    out = tmp_path / "out.dat"
    rc = cli.main(["apply-specs", ALL_A, str(specs), str(out), "--start", "200", "--json"])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert len(report["applied"]) == 1
    assert len(report["skipped"]) == 1
    assert load(CloneImage, str(out)).memory.channels[200].ctcss_hz == 91.5


def test_apply_specs_missing_base_errors(tmp_path, capsys):
    specs = tmp_path / "specs.json"
    specs.write_text("[]")
    rc = cli.main(["apply-specs", "/no/such.dat", str(specs), str(tmp_path / "o.dat")])
    assert rc == 2
    assert "error" in capsys.readouterr().err.lower()


def test_apply_specs_refuses_overwriting_base(tmp_path, capsys):
    specs = tmp_path / "specs.json"
    specs.write_text(json.dumps(SPECS))
    rc = cli.main(["apply-specs", ALL_A, str(specs), ALL_A])
    assert rc == 2
    assert "error" in capsys.readouterr().err.lower()


def _run(tmp_path, payload, capsys):
    specs = tmp_path / "specs.json"
    specs.write_text(json.dumps(payload))
    out = tmp_path / "out.dat"
    rc = cli.main(["apply-specs", ALL_A, str(specs), str(out), "--start", "200", "--json"])
    return rc, out, capsys.readouterr()


@pytest.mark.parametrize("payload", [SPECS[0], [1], ["x"], "x", None])
def test_apply_specs_not_a_list_of_objects_is_an_error(tmp_path, capsys, payload):
    """Malformed spec JSON stays inside the CLI error contract (I2)."""
    rc, out, cap = _run(tmp_path, payload, capsys)
    assert rc == 2
    assert cap.err.startswith("error: specs must be a JSON list of objects")
    assert not out.exists()


@pytest.mark.parametrize(("over", "reason"), [
    ({"name": 123}, "name"),
    ({"name": None, "callsign": 7}, "callsign"),
    ({"mode": ["FM"]}, "mode"),
    ({"ctcss_tx_hz": [1]}, "ctcss_tx_hz"),
    ({"ctcss_rx_hz": {"a": 1}}, "ctcss_rx_hz"),
    ({"rx_frequency_mhz": [146.7]}, "rx"),
    ({"params": [12.5]}, "params"),
])
def test_apply_specs_wrong_typed_field_skips_row(tmp_path, capsys, over, reason):
    rc, out, cap = _run(tmp_path, [{**SPECS[0], **over}, SPECS[0]], capsys)
    assert rc == 0, cap.err
    report = json.loads(cap.out)
    assert len(report["applied"]) == 1 and len(report["skipped"]) == 1
    assert reason in report["skipped"][0]["reason"]
    assert out.exists()


@pytest.mark.parametrize("field", ["rx_frequency_mhz", "tx_frequency_mhz", "mode"])
def test_apply_specs_missing_required_field_skips_row(tmp_path, capsys, field):
    spec = {k: v for k, v in SPECS[0].items() if k != field}
    rc, _, cap = _run(tmp_path, [spec], capsys)
    assert rc == 0, cap.err
    report = json.loads(cap.out)
    assert report["applied"] == []
    assert report["skipped"][0]["reason"] == f"missing {field}"
