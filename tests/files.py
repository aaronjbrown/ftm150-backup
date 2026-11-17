"""Test-only file helpers: the engine is bytes-only, so tests read paths here."""
import os

from ftm150.engine.image import CloneImage, MemoryImage, SetupImage


def read(path: str | os.PathLike[str]) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def load[T: (CloneImage, MemoryImage, SetupImage)](
        cls: type[T], path: str | os.PathLike[str]) -> T:
    """Build an image of exactly ``cls`` from the file at ``path`` (kind-checked)."""
    return cls.from_bytes(read(path))


RADIO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "radio")
ALL_A = os.path.join(RADIO, "ALL_A.dat")
ALL_B = os.path.join(RADIO, "ALL_B.dat")
MEMORY_B = os.path.join(RADIO, "MEMORY_B.dat")
SETUP_B = os.path.join(RADIO, "SETUP_B.dat")
