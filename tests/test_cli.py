import json

import pytest

from ftm150 import CloneImage, cli, csv_io
from tests.files import ALL_A, ALL_B, MEMORY_B, SETUP_B, load


def read(path):
    with open(path, "rb") as fh:
        return fh.read()


def test_info(capsys):
    rc = cli.main(["info", ALL_A])
    out = capsys.readouterr().out
    assert rc == 0
    assert "AH086$ ok" in out
    assert "999" in out


def test_dump_runs(capsys):
    rc = cli.main(["dump", ALL_A])
    assert rc == 0
    assert "RPT2M-A" in capsys.readouterr().out


def test_export_csv(tmp_path):
    out = tmp_path / "chans.csv"
    rc = cli.main(["export-csv", ALL_A, str(out)])
    assert rc == 0
    text = out.read_text()
    assert "RPT2M-A" in text


def test_import_csv_writes_valid_image(tmp_path):
    csvp = tmp_path / "c.csv"
    cli.main(["export-csv", ALL_A, str(csvp)])
    outp = tmp_path / "out.dat"
    rc = cli.main(["import-csv", ALL_A, str(csvp), str(outp)])
    assert rc == 0
    assert outp.stat().st_size == 0x18000


def test_every_sample_dumps(sample_paths, capsys):
    for p in sample_paths:
        assert cli.main(["dump", p]) == 0


def test_cli_does_not_swallow_attribute_error(monkeypatch):
    def boom(args):
        raise AttributeError("programming bug")
    monkeypatch.setattr(cli, "_cmd_dump", boom)
    with pytest.raises(AttributeError):
        cli.main(["dump", ALL_A])


def _all_a_copy(tmp_path):
    f = tmp_path / "a.dat"
    with open(ALL_A, "rb") as fh:
        f.write_bytes(fh.read())
    return f


def test_set_without_out_or_in_place_is_usage_error(tmp_path):
    f = _all_a_copy(tmp_path)
    with pytest.raises(SystemExit) as e:
        cli.main(["set", str(f), "1", "power", "LOW"])
    assert e.value.code == 2


def test_set_out_and_in_place_are_mutually_exclusive(tmp_path):
    f = _all_a_copy(tmp_path)
    with pytest.raises(SystemExit) as e:
        cli.main(["set", str(f), "1", "power", "LOW", "--out", str(tmp_path / "o"),
                  "--in-place"])
    assert e.value.code == 2


def test_set_in_place_edits_file(tmp_path):
    f = _all_a_copy(tmp_path)
    assert cli.main(["set", str(f), "1", "power", "LOW", "--in-place"]) == 0
    assert load(CloneImage, str(f)).memory.channels[1].power == "LOW"


def test_import_csv_refuses_overwriting_base(tmp_path, capsys):
    f = _all_a_copy(tmp_path)
    c = tmp_path / "c.csv"
    assert cli.main(["export-csv", str(f), str(c)]) == 0
    assert cli.main(["import-csv", str(f), str(c), str(f)]) == 2
    assert "--in-place" in capsys.readouterr().err
    assert cli.main(["import-csv", str(f), str(c), str(f), "--in-place"]) == 0


def test_import_csv_chirp_flag(tmp_path):
    c, out = tmp_path / "c.csv", tmp_path / "o.dat"
    assert cli.main(["export-csv", ALL_A, str(c), "--chirp"]) == 0
    assert cli.main(["import-csv", ALL_A, str(c), str(out), "--chirp"]) == 0
    assert out.exists()


def test_export_csv_refuses_overwriting_input(tmp_path, capsys):
    f = _all_a_copy(tmp_path)
    before = f.read_bytes()
    assert cli.main(["export-csv", str(f), str(f)]) == 2
    err = capsys.readouterr().err
    assert "error:" in err and "pass --in-place" not in err   # export-csv has no --in-place
    assert f.read_bytes() == before


def test_apply_specs_in_place_and_specs_path_protected(tmp_path, capsys):
    f = _all_a_copy(tmp_path)
    specs = tmp_path / "s.json"
    specs.write_text("[]")
    assert cli.main(["apply-specs", str(f), str(specs), str(specs)]) == 2
    assert specs.read_text() == "[]"
    assert cli.main(["apply-specs", str(f), str(specs), str(f), "--in-place"]) == 0
    json.loads(specs.read_text())


def test_info_reports_kind(capsys):
    assert cli.main(["info", MEMORY_B]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "kind: MEMORY" and "APO: n/a" in out


def test_info_setup_file_has_no_channel_counts(capsys):
    assert cli.main(["info", SETUP_B]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "kind: SETUP"
    assert "regular channels: n/a (n/a used)" in out and "PMS pairs: n/a" in out


def test_set_in_place_on_memory_file(tmp_path):
    f = tmp_path / "MEMFTM15001.dat"
    f.write_bytes(read(MEMORY_B))
    assert cli.main(["set", str(f), "1", "power", "LOW", "--in-place"]) == 0
    assert f.stat().st_size == 41472


@pytest.mark.parametrize("argv", [
    ["set", SETUP_B, "1", "power", "LOW", "--out", "{out}"],
    ["apply-specs", SETUP_B, "{specs}", "{out}"],
    ["import-csv", SETUP_B, "{csv}", "{out}"],
    ["export-csv", SETUP_B, "{out}"],
    ["dump", SETUP_B],
])
def test_setup_file_where_channels_needed(argv, tmp_path, capsys):
    specs = tmp_path / "s.json"
    specs.write_text("[]")
    csvf = tmp_path / "c.csv"
    csvf.write_text(",".join(csv_io.CSV_COLUMNS) + "\n")
    filled = [a.format(out=tmp_path / "out.dat", specs=specs, csv=csvf) for a in argv]
    assert cli.main(filled) == 2
    assert "SETUP backup has no memory channels" in capsys.readouterr().err
    assert not (tmp_path / "out.dat").exists()


def test_extract_and_merge_cli(tmp_path):
    mem, setup = tmp_path / "MEMFTM15001.dat", tmp_path / "SYSFTM15001.dat"
    assert cli.main(["extract", ALL_B, "memory", str(mem)]) == 0
    assert mem.read_bytes() == read(MEMORY_B)
    assert cli.main(["extract", ALL_B, "SETUP", str(setup)]) == 0
    assert setup.read_bytes() == read(SETUP_B)
    out = tmp_path / "merged.dat"
    assert cli.main(["merge", ALL_A, str(out), "--memory", str(mem), "--setup", str(setup)]) == 0
    assert load(CloneImage, str(out)).memory.to_bytes() == read(MEMORY_B)


def test_merge_requires_a_partial(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["merge", ALL_A, "x.dat"])
    assert excinfo.value.code == 2
    assert "at least one of --memory/--setup" in capsys.readouterr().err


def test_in_place_never_overwrites_extract_input_or_a_partial(tmp_path):
    f = tmp_path / "x.dat"
    f.write_bytes(read(ALL_B))
    assert cli.main(["extract", str(f), "setup", str(f)]) == 2
    assert f.read_bytes() == read(ALL_B)
    m = tmp_path / "m.dat"
    m.write_bytes(read(MEMORY_B))
    b = tmp_path / "b.dat"
    b.write_bytes(read(ALL_A))
    assert cli.main(["merge", str(b), str(m), "--memory", str(m), "--in-place"]) == 2
    assert m.read_bytes() == read(MEMORY_B)


def test_merge_with_non_all_base_fails(tmp_path):
    assert cli.main(["merge", MEMORY_B, str(tmp_path / "o.dat"), "--setup", SETUP_B]) == 2
    assert not (tmp_path / "o.dat").exists()


def test_merge_in_place_on_base(tmp_path):
    b = tmp_path / "b.dat"
    b.write_bytes(read(ALL_A))
    assert cli.main(["merge", str(b), str(b), "--setup", SETUP_B, "--in-place"]) == 0
    assert load(CloneImage, str(b)).setup.to_bytes()[:0x180] == read(SETUP_B)[:0x180]


def _exit_code(argv):
    try:
        return cli.main(argv)
    except SystemExit as e:
        return e.code


def test_extract_refuses_the_old_kind_name(tmp_path):
    out = tmp_path / "o.dat"
    assert _exit_code(["extract", ALL_B, "system", str(out)]) == 2
    assert not out.exists()


def test_merge_refuses_the_old_flag(tmp_path):
    out = tmp_path / "o.dat"
    assert _exit_code(["merge", ALL_A, str(out), "--system", SETUP_B]) == 2
    assert not out.exists()
