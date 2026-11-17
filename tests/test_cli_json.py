# tests/test_cli_json.py
import json
import os

from ftm150 import cli
from tests.files import ALL_A


def test_info_json(capsys):
    rc = cli.main(["info", "--json", ALL_A])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["magic_ok"] is True
    assert data["regular_channels"] == 999
    assert data["used"] >= 1
    assert "apo" in data


def test_dump_json_first_channel(capsys):
    rc = cli.main(["dump", "--json", ALL_A])
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert isinstance(rows, list)
    assert rows[0]["Name"] == "RPT2M-A"
    assert rows[0]["Frequency"] == "146.9"


def test_missing_file_returns_error_code_and_stderr(capsys):
    rc = cli.main(["info", "/no/such/file.dat"])
    assert rc == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error" in captured.err.lower()


def test_write_to_readonly_dir_returns_error_code(tmp_path, capsys):
    if os.geteuid() == 0:
        import pytest
        pytest.skip("chmod-based permission test is meaningless as root")
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o500)  # read+execute, no write
    rc = cli.main(["set", ALL_A, "1", "ctcss_hz", "88.5", "--out", str(ro / "x.dat")])
    assert rc == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error" in captured.err.lower()
