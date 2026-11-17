"""py.typed ships with the package (PEP 561)."""
import itertools
import os
import shutil
import subprocess
import sys
import tomllib
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))


def _version_tuple(v):
    parts = []
    for p in v.split(".")[:2]:
        digits = "".join(itertools.takewhile(str.isdigit, p))
        parts.append(int(digits or 0))
    return tuple(parts)


def test_pyproject_declares_py_typed_package_data():
    with open(os.path.join(ROOT, "pyproject.toml"), "rb") as fh:
        conf = tomllib.load(fh)
    assert "py.typed" in conf["tool"]["setuptools"]["package-data"]["ftm150"]
    assert os.path.isfile(os.path.join(ROOT, "ftm150", "py.typed"))


def test_wheel_ships_py_typed(tmp_path):
    # Offline: no build isolation, so the backend must already be importable.
    setuptools = pytest.importorskip(
        "setuptools", reason="build backend (setuptools) unavailable offline")
    pytest.importorskip("pip", reason="pip unavailable")
    if _version_tuple(setuptools.__version__) < (70, 1):   # bdist_wheel moved into setuptools
        pytest.importorskip("wheel", reason="old setuptools needs the wheel package")
    src = tmp_path / "src"
    shutil.copytree(os.path.join(ROOT, "ftm150"), src / "ftm150",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(os.path.join(ROOT, "pyproject.toml"), src)
    dist = tmp_path / "dist"
    r = subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-index",
                        "--no-build-isolation", "-w", str(dist), str(src)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    (wheel,) = dist.glob("ftm150-*.whl")
    names = zipfile.ZipFile(wheel).namelist()
    assert "ftm150/py.typed" in names
    assert "ftm150/schemas/repeater_spec.schema.json" in names
