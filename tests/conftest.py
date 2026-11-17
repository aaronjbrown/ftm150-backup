import pytest

from tests.files import ALL_A, ALL_B


def _read(path):
    with open(path, "rb") as fh:
        return fh.read()


@pytest.fixture(scope="session")
def sample_paths():
    return [ALL_A, ALL_B]


@pytest.fixture(scope="session")
def read_bytes():
    return _read


@pytest.fixture
def blank():
    """A synthetic all-zero image and its CH1 (rec at 0x800)."""
    from ftm150.engine.image import CloneImage
    img = CloneImage(bytes(0x18000))
    return img, img.memory.channels[1]
