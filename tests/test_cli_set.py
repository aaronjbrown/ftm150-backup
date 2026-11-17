# tests/test_cli_set.py

from ftm150 import CloneImage, cli
from ftm150.engine import layout
from tests.files import ALL_A, load


def test_set_ctcss_writes_out(tmp_path):
    out = tmp_path / "out.dat"
    rc = cli.main(["set", ALL_A, "1", "ctcss_hz", "88.5", "--out", str(out)])
    assert rc == 0
    assert load(CloneImage, str(out)).memory.channels[1].ctcss_hz == 88.5


def test_set_power_by_name(tmp_path):
    out = tmp_path / "out.dat"
    rc = cli.main(["set", ALL_A, "1", "power", "LOW", "--out", str(out)])
    assert rc == 0
    assert load(CloneImage, str(out)).memory.channels[1].power == "LOW"


def test_set_band_by_name(tmp_path):
    out = tmp_path / "out.dat"
    rc = cli.main(["set", ALL_A, "1", "band", "VHF", "--out", str(out)])
    assert rc == 0
    assert load(CloneImage, str(out)).memory.channels[1].band.name == "VHF"


def test_set_edit_is_local(tmp_path):
    """Setting one field must change only that field's bits; every other
    enabled channel's raw record is untouched."""
    out = tmp_path / "out.dat"
    before = load(CloneImage, ALL_A)
    cli.main(["set", ALL_A, "1", "ctcss_hz", "88.5", "--out", str(out)])
    after = load(CloneImage, str(out))
    for n in range(2, layout.NUM_REGULAR + 1):
        if before.memory.channels[n].enabled:
            assert before.memory.channels[n].raw == after.memory.channels[n].raw, n


def test_set_invalid_ctcss_returns_error_and_no_write(tmp_path, capsys):
    out = tmp_path / "out.dat"
    rc = cli.main(["set", ALL_A, "1", "ctcss_hz", "99.9", "--out", str(out)])
    assert rc == 2
    assert "error" in capsys.readouterr().err.lower()
    assert not out.exists()


def test_set_unknown_field_returns_error(tmp_path, capsys):
    out = tmp_path / "out.dat"
    rc = cli.main(["set", ALL_A, "1", "bogusfield", "v", "--out", str(out)])
    assert rc == 2
    err = capsys.readouterr().err
    assert err.startswith("error: ") and "unknown field 'bogusfield'" in err
    assert not out.exists()


def test_set_out_equal_to_file_is_refused(tmp_path, capsys):
    f = tmp_path / "f.dat"
    with open(ALL_A, "rb") as fh:
        f.write_bytes(fh.read())
    before = f.read_bytes()
    rc = cli.main(["set", str(f), "1", "power", "LOW", "--out", str(f)])
    assert rc == 2
    err = capsys.readouterr().err
    assert err.startswith("error: ") and "--in-place" in err
    assert f.read_bytes() == before


def test_set_invalid_mode_returns_error_and_no_write(tmp_path, capsys):
    out = tmp_path / "out.dat"
    rc = cli.main(["set", ALL_A, "1", "mode", "BOGUS", "--out", str(out)])
    assert rc == 2
    assert "error" in capsys.readouterr().err.lower()
    assert not out.exists()


def test_set_valid_mode_am_writes(tmp_path):
    out = tmp_path / "out.dat"
    rc = cli.main(["set", ALL_A, "1", "mode", "am", "--out", str(out)])
    assert rc == 0
    assert load(CloneImage, str(out)).memory.channels[1].mode == "AM"


def test_set_mhz_alias_is_exact(tmp_path):
    out = tmp_path / "out.dat"
    rc = cli.main(["set", ALL_A, "1", "rx_mhz", " 146.6000 ", "--out", str(out)])
    assert rc == 0
    assert load(CloneImage, str(out)).memory.channels[1].rx_hz == 146_600_000
    out2 = tmp_path / "out2.dat"
    rc = cli.main(["set", str(out), "1", "offset_khz", "5000", "--out", str(out2)])
    assert rc == 0
    assert load(CloneImage, str(out2)).memory.channels[1].offset_hz == 5_000_000


def test_set_off_grid_mhz_refused(tmp_path, capsys):
    out = tmp_path / "out.dat"
    rc = cli.main(["set", ALL_A, "1", "rx_mhz", "146.65125", "--out", str(out)])
    assert rc == 2 and "2.5 kHz" in capsys.readouterr().err
    assert not out.exists()


def test_set_engine_hz_name_refused(tmp_path, capsys):
    out = tmp_path / "out.dat"
    rc = cli.main(["set", ALL_A, "1", "rx_hz", "146650000", "--out", str(out)])
    assert rc == 2 and "unknown field" in capsys.readouterr().err
    assert not out.exists()


def test_set_digit_band_is_range_checked(tmp_path, capsys):
    """A decoded band given as its code (0-3) is validated like its name (I1)."""
    out = tmp_path / "out.dat"
    rc = cli.main(["set", ALL_A, "1", "band", "3", "--out", str(out)])   # CH1 is VHF 146.9
    assert rc == 2
    assert "outside band UHF" in capsys.readouterr().err
    assert not out.exists()


def test_set_digit_band_in_range_reads_back_as_band(tmp_path):
    from ftm150.engine.tables import Band
    out = tmp_path / "out.dat"
    assert cli.main(["set", ALL_A, "1", "band", "1", "--out", str(out)]) == 0
    assert load(CloneImage, str(out)).memory.channels[1].band is Band.VHF


def test_set_long_name_refused(tmp_path, capsys):
    """A name over 8 characters is refused, not silently truncated."""
    out = tmp_path / "out.dat"
    rc = cli.main(["set", ALL_A, "1", "name", "A" * 9, "--out", str(out)])
    assert rc == 2
    assert "longer than 8" in capsys.readouterr().err
    assert not out.exists()


def test_set_step_auto_refused(tmp_path, capsys):
    out = tmp_path / "out.dat"
    rc = cli.main(["set", ALL_A, "1", "step_khz", "AUTO", "--out", str(out)])
    assert rc == 2
    assert "no AUTO step" in capsys.readouterr().err
    assert not out.exists()
