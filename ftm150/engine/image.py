"""Backup images: an ALL clone composed of MEMORY and SETUP views over one buffer.

Every image holds a CLN-sized (ALL) ``bytearray``. A MEMORY or SETUP file loaded on its
own is expanded into a private buffer (spec 2b block maps); ``CloneImage.memory`` and
``CloneImage.setup`` are views sharing the clone's buffer, so edits through them show in
``CloneImage.to_bytes()``. Each view exposes only the records its file both carries and a
restore applies (spec 2b "Restore behaviour" exposure list).
"""
from collections.abc import Iterator
from typing import ClassVar, Self

from . import layout, partial
from .partial import Kind
from .record import Channel
from .settings import Settings


class _ChannelList:
    """1-based sequence of the regular channels."""
    def __init__(self, buf: bytearray) -> None:
        self._buf = buf

    def __len__(self) -> int:
        return layout.NUM_REGULAR

    def _make(self, n: int) -> Channel:
        off = layout.CH_BASE + (n - 1) * layout.CH_STRIDE
        name = layout.NAME_BASE + (n - 1) * layout.CH_STRIDE
        flag = layout.NAME_FLAG_BASE + (n - 1) * layout.NAME_FLAG_STRIDE
        return Channel(self._buf, off, name, flag, number=n)

    def __getitem__(self, n: int) -> Channel:
        if not (1 <= n <= layout.NUM_REGULAR):
            raise IndexError(f"channel {n} out of range 1..{layout.NUM_REGULAR}")
        return self._make(n)

    def __iter__(self) -> Iterator[Channel]:
        for _, ch in self.items():
            yield ch

    def items(self) -> Iterator[tuple[int, Channel]]:
        for n in range(1, layout.NUM_REGULAR + 1):
            yield n, self._make(n)


class _PmsPair:
    def __init__(self, buf: bytearray, base: int) -> None:
        self.lower = Channel(buf, base, None)
        self.upper = Channel(buf, base + layout.CH_STRIDE, None)


class _PmsList:
    def __init__(self, buf: bytearray) -> None:
        self._buf = buf

    def __len__(self) -> int:
        return layout.NUM_PMS_PAIRS

    def __getitem__(self, n: int) -> _PmsPair:
        if not (1 <= n <= layout.NUM_PMS_PAIRS):
            raise IndexError(f"PMS pair {n} out of range 1..{layout.NUM_PMS_PAIRS}")
        return _PmsPair(self._buf, layout.PMS_BASE + (n - 1) * layout.PMS_PAIR_STRIDE)

    def __iter__(self) -> Iterator[_PmsPair]:
        for n in range(1, layout.NUM_PMS_PAIRS + 1):
            yield self[n]

    def items(self) -> Iterator[tuple[int, _PmsPair]]:
        for n in range(1, layout.NUM_PMS_PAIRS + 1):
            yield n, self[n]


class _BandMap:
    def __init__(self, buf: bytearray, base: int) -> None:
        self._buf = buf
        self._base = base

    def __getitem__(self, band: int) -> Channel:
        return Channel(self._buf, self._base + int(band) * layout.BAND_STRIDE, None)


MERGE_NEEDS_PARTIAL = "merge needs a MEMORY and/or SETUP backup"


class NotInBackup(ValueError):  # noqa: N818 - public name fixed by the design
    """The requested record or setting is not carried by this kind of backup."""


def _check_kind(data: bytes, kind: Kind) -> None:
    got = partial.detect_kind(data)
    if got != kind:
        raise ValueError(
            f"expected {kind} backup ({partial.LAYOUTS[kind].size} bytes), got {len(data)} "
            f"bytes ({got} backup); backup sizes are {partial.LAYOUTS[Kind.ALL].size} "
            f"(ALL), {partial.LAYOUTS[Kind.MEMORY].size} (MEMORY), "
            f"{partial.LAYOUTS[Kind.SETUP].size} (SETUP)"
        )


class _Backup:
    """Behaviour shared by every backup kind; ``_buf`` is always ALL-sized."""
    kind: ClassVar[Kind]
    _buf: bytearray

    @classmethod
    def from_bytes(cls, data: bytes) -> Self:
        raise NotImplementedError

    @property
    def magic_ok(self) -> bool:
        return bytes(self._buf[:len(layout.MAGIC)]) == layout.MAGIC

    def to_bytes(self) -> bytes:
        """This kind's own file format (ALL 98304 B, MEMORY 41472 B, SETUP 1024 B)."""
        return partial.extract(bytes(self._buf), self.kind)


class _View(_Backup):
    def __init__(self, buf: bytearray) -> None:
        if len(buf) != partial.LAYOUTS[Kind.ALL].size:
            raise ValueError(
                f"view buffer must be {partial.LAYOUTS[Kind.ALL].size} bytes, got {len(buf)}")
        self._buf = buf

    @classmethod
    def from_bytes(cls, data: bytes) -> Self:
        _check_kind(data, cls.kind)
        return cls(partial.expand(data, cls.kind))


class MemoryImage(_View):
    """MEMORY backup (MEMFTM150nn.dat): channels, PMS, Home A, Home B."""
    kind = Kind.MEMORY

    def __init__(self, buf: bytearray) -> None:
        super().__init__(buf)
        self.channels = _ChannelList(self._buf)
        self.pms = _PmsList(self._buf)
        self.home_a = _BandMap(self._buf, layout.HOME_A_BASE)
        self.home_b = _BandMap(self._buf, layout.HOME_B_BASE)


class SetupImage(_View):
    """SETUP backup (SYSFTM150nn.dat): set-menu settings, VFO A, VFO B."""
    kind = Kind.SETUP

    def __init__(self, buf: bytearray) -> None:
        super().__init__(buf)
        self.settings = Settings(self._buf)
        self.vfo_a = _BandMap(self._buf, layout.VFO_A_BASE)
        self.vfo_b = _BandMap(self._buf, layout.VFO_B_BASE)


class CloneImage(_Backup):
    """ALL backup (CLNFTM150nn.dat) composed of ``.memory`` and ``.setup`` views."""
    kind = Kind.ALL

    def __init__(self, data: bytes) -> None:
        _check_kind(data, Kind.ALL)
        self._buf = bytearray(data)
        self._memory = MemoryImage(self._buf)
        self._setup = SetupImage(self._buf)

    @classmethod
    def from_bytes(cls, data: bytes) -> Self:
        return cls(data)

    @property
    def memory(self) -> MemoryImage:
        return self._memory

    @property
    def setup(self) -> SetupImage:
        return self._setup

    def merge(self, memory: MemoryImage | None = None, setup: SetupImage | None = None) -> None:
        """Overlay MEMORY and/or SETUP backups onto this image, in place (spec 2b).

        Only each kind's owner-masked ranges are copied, so a single partial never
        touches the other owner's slice. Everything is validated before any write.
        """
        if memory is None and setup is None:
            raise ValueError(MERGE_NEEDS_PARTIAL)
        given: list[tuple[Kind, _View | None, type[_View]]] = [
            (Kind.MEMORY, memory, MemoryImage), (Kind.SETUP, setup, SetupImage)]
        hdr = partial.HEADER
        todo: list[_View] = []
        for kind, img, cls in given:
            if img is None:
                continue
            if not isinstance(img, cls):
                raise ValueError(f"expected a {kind} backup, got {type(img).__name__}")
            if self._buf[hdr.lo:hdr.hi] != img._buf[hdr.lo:hdr.hi]:
                raise ValueError(f"header block differs between base and {kind} backup")
            todo.append(img)
        for img in todo:
            for lo, hi in partial.merge_ranges(img.kind):
                self._buf[lo:hi] = img._buf[lo:hi]  # in place: views share this buffer


def image_from_bytes(data: bytes) -> CloneImage | MemoryImage | SetupImage:
    """Build the image for any backup kind, dispatching on its size."""
    kind = partial.detect_kind(data)
    if kind == Kind.ALL:
        return CloneImage(data)
    if kind == Kind.MEMORY:
        return MemoryImage.from_bytes(data)
    return SetupImage.from_bytes(data)
