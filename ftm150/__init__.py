import importlib.metadata

from .engine import layout, tables
from .engine.image import CloneImage, MemoryImage, NotInBackup, SetupImage
from .engine.record import Channel
from .engine.tables import Band
from .interop import chirp, csv_io
from .ops import load_image, save_image

try:
    __version__ = importlib.metadata.version("ftm150")
except importlib.metadata.PackageNotFoundError:   # uninstalled source tree
    __version__ = "0+unknown"

__all__ = [
    "Band",
    "Channel",
    "CloneImage",
    "MemoryImage",
    "NotInBackup",
    "SetupImage",
    "chirp",
    "csv_io",
    "layout",
    "load_image",
    "save_image",
    "tables",
]
