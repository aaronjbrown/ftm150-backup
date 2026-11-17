import os

import pytest

from ftm150.fileio import atomic_write, resolve_output


def test_alias_spellings_refused(tmp_path, monkeypatch):
    f = tmp_path / "x.dat"
    f.write_bytes(b"1")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "link.dat").symlink_to(f)
    for out in ["x.dat", "./x.dat", str(f), "link.dat"]:
        with pytest.raises(ValueError):
            resolve_output(str(f), out)


def test_hard_link_refused(tmp_path):
    f = tmp_path / "x.dat"
    f.write_bytes(b"1")
    os.link(f, tmp_path / "hard.dat")
    with pytest.raises(ValueError):
        resolve_output(str(f), str(tmp_path / "hard.dat"))


def test_in_place_rules(tmp_path):
    f = str(tmp_path / "x.dat")
    m = str(tmp_path / "m.dat")
    assert resolve_output(f, None, in_place=True) == f
    with pytest.raises(ValueError, match="not allowed"):
        resolve_output(f, f, in_place=True, same_kind=False)
    with pytest.raises(ValueError):
        resolve_output(f, m, others=[m], in_place=True)


def test_messages(tmp_path):
    f = str(tmp_path / "x.dat")
    with pytest.raises(ValueError, match=r"output path is required \(or --in-place\)"):
        resolve_output(f, None)
    with pytest.raises(ValueError, match="pass --in-place to overwrite it"):
        resolve_output(f, f)
    assert resolve_output(f, f, in_place=True) == f
    assert resolve_output(f, str(tmp_path / "o.dat")) == str(tmp_path / "o.dat")


def test_atomic_write_failure_keeps_original(tmp_path, monkeypatch):
    f = tmp_path / "x.dat"
    f.write_bytes(b"orig")
    monkeypatch.setattr(os, "replace", lambda *a: (_ for _ in ()).throw(OSError("boom")))
    with pytest.raises(OSError):
        atomic_write(f, b"new")
    assert f.read_bytes() == b"orig"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["x.dat"]


def test_atomic_write_ok_and_mode(tmp_path):
    f = tmp_path / "x.dat"
    f.write_bytes(b"orig")
    f.chmod(0o640)
    atomic_write(f, b"new")
    assert f.read_bytes() == b"new"
    assert f.stat().st_mode & 0o777 == 0o640
    assert [p.name for p in tmp_path.iterdir()] == ["x.dat"]
    g = tmp_path / "new.dat"
    atomic_write(str(g), b"z")
    assert g.read_bytes() == b"z"


def test_atomic_write_through_symlink(tmp_path):
    real = tmp_path / "real.dat"
    real.write_bytes(b"old")
    link = tmp_path / "link.dat"
    link.symlink_to(real)
    atomic_write(link, b"new")
    assert os.path.islink(link)
    assert real.read_bytes() == b"new"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["link.dat", "real.dat"]


def test_atomic_write_new_file_honours_umask(tmp_path):
    old = os.umask(0o027)
    try:
        g = tmp_path / "n.dat"
        atomic_write(g, b"z")
    finally:
        os.umask(old)
    assert g.stat().st_mode & 0o777 == 0o640


def test_atomic_write_temp_never_looser_than_target(tmp_path, monkeypatch):
    f = tmp_path / "s.dat"
    f.write_bytes(b"secret")
    f.chmod(0o600)
    real_fdopen = os.fdopen
    seen = []

    def checking_fdopen(fd, *a, **k):
        seen.append(os.fstat(fd).st_mode & 0o777)  # before any data is written
        return real_fdopen(fd, *a, **k)

    monkeypatch.setattr(os, "fdopen", checking_fdopen)
    atomic_write(f, b"new")
    assert seen == [0o600]
    assert f.stat().st_mode & 0o777 == 0o600
    assert f.read_bytes() == b"new"


def test_same_kind_false_message_has_no_in_place_hint(tmp_path):
    """export-csv / extract have no --in-place: don't suggest it (M1)."""
    f = str(tmp_path / "x.dat")
    for in_place in (False, True):
        with pytest.raises(ValueError) as ei:
            resolve_output(f, f, in_place=in_place, same_kind=False)
        msg = str(ei.value)
        assert "out must differ from the input" in msg and "not allowed" in msg
        assert "pass --in-place" not in msg


def test_atomic_write_closes_fd_when_fchmod_fails(tmp_path, monkeypatch):
    """A failure before os.fdopen owns the fd must still close it (no fd leak)."""
    f = tmp_path / "x.dat"
    f.write_bytes(b"orig")
    real_open, opened = os.open, []

    def recording_open(*a, **k):
        fd = real_open(*a, **k)
        opened.append(fd)
        return fd

    def failing_fchmod(fd, mode):
        raise OSError("fchmod boom")

    monkeypatch.setattr(os, "open", recording_open)
    monkeypatch.setattr(os, "fchmod", failing_fchmod)
    with pytest.raises(OSError, match="fchmod boom"):
        atomic_write(f, b"new")
    monkeypatch.undo()
    assert len(opened) == 1
    with pytest.raises(OSError):
        os.fstat(opened[0])                     # closed: EBADF
    assert f.read_bytes() == b"orig"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["x.dat"]
