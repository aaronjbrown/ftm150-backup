"""MEMORY / SETUP partial backups as block selections of the ALL image (spec 2b)."""

from dataclasses import dataclass
from enum import StrEnum
from typing import NamedTuple


class Kind(StrEnum):
    """Backup kind; str()/f-strings/JSON render the bare value (``MEMORY``)."""

    ALL = "ALL"
    MEMORY = "MEMORY"
    SETUP = "SETUP"


class Span(NamedTuple):
    """Half-open CLN byte range [lo, hi)."""

    lo: int
    hi: int


class Block(NamedTuple):
    """A run copied verbatim between a partial file and the ALL image."""

    file_off: int
    cln_off: int
    length: int

    @property
    def cln(self) -> Span:
        return Span(self.cln_off, self.cln_off + self.length)


@dataclass(frozen=True)
class Layout:
    """How one backup kind maps onto the ALL image."""

    size: int
    blocks: tuple[Block, ...]  # () for ALL
    owns: Span | None  # this kind's half of SHARED; None for ALL


HEADER = Span(0x000, 0x080)  # identical in all kinds; compared on merge, never copied
SHARED = Span(0x180, 0x200)  # carried by both partials; split by owner (spec 2b restore table)

LAYOUTS: dict[Kind, Layout] = {
    Kind.ALL: Layout(size=0x18000, blocks=(), owns=None),
    Kind.MEMORY: Layout(
        size=0xA200,
        blocks=(
            Block(0x0000, 0x00000, 0x80),
            Block(0x0080, 0x00180, 0x100),
            Block(0x0180, 0x00480, 0x80),
            Block(0x0200, 0x00800, 0x5A00),
            Block(0x5C00, 0x10000, 0x4600),
        ),
        owns=Span(0x1A0, 0x200),  # Home A and Home B slot 0
    ),
    Kind.SETUP: Layout(
        size=0x400,
        blocks=(
            Block(0x000, 0x000, 0x200),
            Block(0x200, 0x280, 0x80),
            Block(0x280, 0x500, 0x80),
        ),
        owns=Span(0x180, 0x1A0),  # VFO B slots 3-4
    ),
}


def detect_kind(data: bytes) -> Kind:
    for kind in Kind:
        if len(data) == LAYOUTS[kind].size:
            return kind
    raise ValueError(
        f"unrecognised backup size {len(data)}; expected "
        f"{LAYOUTS[Kind.ALL].size} (ALL), {LAYOUTS[Kind.MEMORY].size} (MEMORY) "
        f"or {LAYOUTS[Kind.SETUP].size} (SETUP)"
    )


def expand(data: bytes, kind: Kind) -> bytearray:
    """Place a backup into a full-size ALL image; uncovered bytes are 0xFF."""
    if len(data) != LAYOUTS[kind].size:
        raise ValueError(f"{kind} backup must be {LAYOUTS[kind].size} bytes, got {len(data)}")
    if kind == Kind.ALL:
        return bytearray(data)
    buf = bytearray(b"\xff" * LAYOUTS[Kind.ALL].size)
    for f, c, n in LAYOUTS[kind].blocks:
        buf[c : c + n] = data[f : f + n]
    return buf


def extract(buf: bytes, kind: Kind) -> bytes:
    """Build a backup of ``kind`` from a full ALL image; unmapped tail is 0xFF."""
    if len(buf) != LAYOUTS[Kind.ALL].size:
        raise ValueError(f"ALL image must be {LAYOUTS[Kind.ALL].size} bytes, got {len(buf)}")
    if kind == Kind.ALL:
        return bytes(buf)
    out = bytearray(b"\xff" * LAYOUTS[kind].size)
    for f, c, n in LAYOUTS[kind].blocks:
        out[f : f + n] = buf[c : c + n]
    return bytes(out)


def _coalesce(spans: list[Span]) -> list[Span]:
    out: list[Span] = []
    for lo, hi in sorted(spans):
        if lo >= hi:
            continue
        if out and lo <= out[-1].hi:
            out[-1] = Span(out[-1].lo, max(out[-1].hi, hi))
        else:
            out.append(Span(lo, hi))
    return out


def _mapped(kind: Kind) -> list[Span]:
    return _coalesce([b.cln for b in LAYOUTS[kind].blocks])


def covers(kind: Kind, lo: int, hi: int) -> bool:
    """True if CLN range [lo, hi) lies within the kind's mapped ranges."""
    if kind == Kind.ALL:
        return True
    return any(a <= lo and hi <= b for a, b in _mapped(kind))


def _subtract(spans: list[Span], cut: Span) -> list[Span]:
    out: list[Span] = []
    for lo, hi in spans:
        if hi <= cut.lo or lo >= cut.hi:
            out.append(Span(lo, hi))
            continue
        if lo < cut.lo:
            out.append(Span(lo, cut.lo))
        if hi > cut.hi:
            out.append(Span(cut.hi, hi))
    return out


def merge_ranges(kind: Kind) -> list[Span]:
    """CLN [lo, hi) ranges that partial ``kind`` writes on merge (no header,
    owner-masked). An ALL image is never merged: ValueError."""
    owns = LAYOUTS[kind].owns
    if owns is None:
        raise ValueError(f"merge_ranges: {kind} is not a partial backup kind")
    rs = _subtract(_mapped(kind), HEADER)
    # SHARED is carried by both partials: keep only this kind's ``owns`` part of it
    rs = _subtract(rs, Span(SHARED.lo, owns.lo))  # the other owner's part below ours
    rs = _subtract(rs, Span(owns.hi, SHARED.hi))  # ... and above ours
    return _coalesce(rs)


def partial_kinds() -> tuple[Kind, ...]:
    """The kinds that are partial backups of an ALL image (every kind but ALL)."""
    return tuple(k for k in Kind if k is not Kind.ALL)
