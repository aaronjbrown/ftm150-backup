import importlib.metadata
import importlib.resources
import os
import subprocess
import sys

import ftm150


def test_mcp_server_imports():
    # Kept local: importing the server (optional `mcp` extra) is what this tests.
    from ftm150.mcp import server
    assert server.mcp.name == "ftm150"
    assert callable(server.main)


def test_package_metadata():
    assert ftm150.__version__ == importlib.metadata.version("ftm150")
    assert importlib.resources.files("ftm150").joinpath("py.typed").is_file()
    assert {"CloneImage", "Channel", "Band"} <= set(ftm150.__all__)


def test_version_falls_back_when_not_installed():
    code = ("import importlib.metadata as m\n"
            "def missing(name):\n"
            "    raise m.PackageNotFoundError(name)\n"
            "m.version = missing\n"
            "import ftm150\n"
            "assert ftm150.__version__ == '0+unknown', ftm150.__version__\n")
    # -P: don't put the CWD on sys.path
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    r = subprocess.run([sys.executable, "-P", "-c", code], capture_output=True, text=True,
                       cwd=root)
    assert r.returncode == 0, r.stderr
