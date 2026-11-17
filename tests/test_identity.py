from ftm150 import CloneImage
from tests.files import load


def test_load_to_bytes_is_identical(sample_paths, read_bytes):
    for path in sample_paths:
        img = load(CloneImage, path)
        assert img.to_bytes() == read_bytes(path), path


def test_magic_ok(sample_paths):
    for path in sample_paths:
        assert load(CloneImage, path).magic_ok, path
