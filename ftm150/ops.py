"""Service layer: the single load -> validate all -> apply -> save core that the
CLI and MCP adapters call.

Every write goes through fileio.resolve_output (never over an input unless
in_place, and in_place only over the primary input of the same kind) and is
saved atomically. import_csv and apply_specs build every record before any
write_record, so a bad row leaves nothing written and no output file.
"""
import csv
import dataclasses
import io
import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import NamedTuple

from . import coerce
from .engine import layout, partial
from .engine.image import (
    MERGE_NEEDS_PARTIAL,
    CloneImage,
    MemoryImage,
    NotInBackup,
    SetupImage,
    image_from_bytes,
)
from .engine.partial import Kind
from .engine.record import Channel, ChannelRecord, write_record
from .fileio import atomic_write, resolve_output
from .interop import chirp as chirp_io
from .interop import csv_io
from .interop.repeater_spec import (
    Applied,
    ApplyResult,
    Skipped,
    UnrepresentableError,
    spec_to_record,
)
from .units import hz_to_mhz

type AnyImage = CloneImage | MemoryImage | SetupImage
type PathLike = str | os.PathLike[str]


def _read(path: PathLike) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def load_image(path: PathLike) -> AnyImage:
    """Load any backup kind, dispatching on file size."""
    return image_from_bytes(_read(path))


def save_image(img: AnyImage, path: PathLike) -> None:
    """Write the image's own file format to PATH atomically. Unlike the commands
    below it does no input-clobber check: the caller has chosen PATH."""
    atomic_write(path, img.to_bytes())


def memory_of(img: AnyImage) -> MemoryImage:
    """The image's memory channels (an ALL's view, or a MEMORY backup itself)."""
    if isinstance(img, CloneImage):
        return img.memory
    if isinstance(img, MemoryImage):
        return img
    raise NotInBackup(f"{img.kind} backup has no memory channels")


def setup_of(img: AnyImage) -> SetupImage:
    """The image's settings/VFO (an ALL's view, or a SETUP backup itself)."""
    if isinstance(img, CloneImage):
        return img.setup
    if isinstance(img, SetupImage):
        return img
    raise NotInBackup(f"{img.kind} backup has no settings")


def _load_memory(path: str) -> tuple[AnyImage, MemoryImage]:
    """Load any kind; raise NotInBackup at once if it carries no memory channels."""
    img = load_image(path)
    return img, memory_of(img)


def info(path: str) -> dict[str, object]:
    """Kind, magic and counts; a value the backup kind does not carry is None."""
    img = load_image(path)
    mem = None if isinstance(img, SetupImage) else memory_of(img)
    setup = None if isinstance(img, MemoryImage) else setup_of(img)
    return {
        "kind": img.kind,
        "magic_ok": img.magic_ok,
        "regular_channels": len(mem.channels) if mem else None,
        "used": sum(1 for c in mem.channels if c.enabled) if mem else None,
        "pms_pairs": len(mem.pms) if mem else None,
        "apo": setup.settings.apo if setup else None,
    }


def _enabled(mem: MemoryImage) -> Iterable[tuple[int, ChannelRecord]]:
    return ((n, ch.to_record()) for n, ch in mem.channels.items() if ch.enabled)


def rows(path: str) -> list[dict[str, object]]:
    """Native CSV rows (typed values, see csv_io.record_to_row) of enabled channels."""
    _, mem = _load_memory(path)
    return [csv_io.record_to_row(n, rec) for n, rec in _enabled(mem)]


def set_field(path: str, channel: int, field: str, value: str, out: str | None = None,
              *, in_place: bool = False) -> dict[str, object]:
    """Set one field on one channel; return the MCP result shape.

    Write to ``out`` or, with ``in_place``, over ``path``; giving both is refused.
    """
    if in_place and out is not None:
        raise ValueError("give an output path or in_place, not both")
    out = resolve_output(path, out, in_place=in_place)
    img, mem = _load_memory(path)
    engine_field, parsed = coerce.coerce(field, value)
    setattr(mem.channels[channel], engine_field, parsed)
    save_image(img, out)
    return {"channel": channel, "field": field, "value": coerce.display(field, parsed),
            "out_path": out}


def export_csv(path: str, out: str, *, chirp: bool = False) -> int:
    """Write the enabled channels as a native (or CHIRP) CSV; return rows written."""
    out = resolve_output(path, out, same_kind=False)
    _, mem = _load_memory(path)
    to_row: Callable[[int, ChannelRecord], dict[str, object] | dict[str, str]]
    if chirp:
        columns, to_row = chirp_io.CHIRP_COLUMNS, chirp_io.record_to_chirp
    else:
        columns, to_row = csv_io.CSV_COLUMNS, csv_io.record_to_row
    out_rows = [to_row(n, rec) for n, rec in _enabled(mem)]
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=columns)
    w.writeheader()
    w.writerows(out_rows)
    atomic_write(out, buf.getvalue().encode("utf-8"))
    return len(out_rows)


def _location(row: dict[str, str]) -> int:
    if "Location" not in row:
        raise ValueError("CSV has no Location column")
    loc = row["Location"]
    text = str(loc).strip()
    # plain ASCII digits only: int() would also take "+5", "1_0" and non-ASCII digits
    n = int(text) if text.isascii() and text.isdigit() else 0
    if not (1 <= n <= layout.NUM_REGULAR):
        raise ValueError(f"Location {loc!r}: not a channel number 1..{layout.NUM_REGULAR}")
    return n


def _native_record(mem: MemoryImage, row: dict[str, str]) -> tuple[int, ChannelRecord]:
    n = _location(row)
    ch = mem.channels[n]
    try:
        # absent ShowName (pre-ShowName CSVs): keep the base's display
        return n, csv_io.row_to_record(row, show_name_default=ch.show_name)
    except (ValueError, KeyError) as e:
        raise ValueError(f"CH{n}: {e}") from None


def _chirp_record(mem: MemoryImage, row: dict[str, str]) -> tuple[int, ChannelRecord]:
    """CHIRP-carried fields over the target's own record; CHIRP_DEFAULTS fill the
    fields CHIRP lacks only when the target is empty. ShowName is the target's."""
    _location(row)                                # range-check before parsing
    n, fields = chirp_io.chirp_to_fields(row)     # errors already "CH{n}: "
    target = mem.channels[n]
    base = target.to_record()
    if not target.enabled:
        base = dataclasses.replace(base, **chirp_io.CHIRP_DEFAULTS)
    return n, dataclasses.replace(base, **fields, enabled=True)


def _write_all(records: list[tuple[Channel, ChannelRecord]]) -> None:
    for ch, rec in records:
        try:
            write_record(ch, rec)
        except (ValueError, KeyError) as e:
            raise ValueError(f"CH{ch.number}: {e}") from None


class Imported(NamedTuple):
    """import_csv's result: rows applied and the resolved output path."""

    rows: int
    out_path: str


def import_csv(base: str, csv_path: str, out: str | None, *, chirp: bool = False,
               in_place: bool = False) -> Imported:
    """Apply a native (or CHIRP) CSV onto BASE; save to OUT (or BASE if in_place).
    Returns the rows applied and the path written."""
    out = resolve_output(base, out, others=[csv_path], in_place=in_place)
    img, mem = _load_memory(base)
    build = _chirp_record if chirp else _native_record
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        try:
            built = [build(mem, row) for row in reader]           # validate all first
        except csv.Error as e:
            raise ValueError(f"CSV line {reader.line_num}: {e}") from None
    _write_all([(mem.channels[n], rec) for n, rec in built])
    save_image(img, out)
    return Imported(len(built), out)


def _first_empty_channel(mem: MemoryImage) -> int:
    for n, ch in mem.channels.items():
        if not ch.enabled:
            return n
    raise ValueError("no empty channel available")


def apply_specs(base: str, specs: list[dict[str, object]], out: str | None, *,
                start: int | None = None, in_place: bool = False,
                protect: Sequence[str] = ()) -> ApplyResult:
    """Write RepeaterSpec rows onto consecutive channels from `start` (default:
    the first empty channel). Unrepresentable specs are skipped and take no
    channel; an occupied channel is overwritten with a note. `protect` lists
    extra input paths (e.g. the specs file) that OUT may never equal.
    `specs` must be a list of objects (ValueError otherwise); a malformed
    object is skipped with a reason like an unrepresentable one."""
    if not (isinstance(specs, list) and all(isinstance(s, Mapping) for s in specs)):
        raise ValueError("specs must be a JSON list of objects")
    out = resolve_output(base, out, others=protect, in_place=in_place)
    img, mem = _load_memory(base)
    channel = _first_empty_channel(mem) if start is None else start
    if not (1 <= channel <= layout.NUM_REGULAR):
        raise ValueError(f"start channel {channel} out of range 1..{layout.NUM_REGULAR}")
    planned: list[tuple[Channel, ChannelRecord]] = []
    applied, skipped = [], []
    for spec in specs:
        ch = mem.channels[channel] if channel <= layout.NUM_REGULAR else None
        try:   # past NUM_REGULAR the placeholder 0 is never written: we raise below
            rec, notes = spec_to_record(spec, user_ctcss_hz=ch.user_ctcss_hz if ch else 0)
        except UnrepresentableError as exc:
            skipped.append(Skipped(spec.get("source_id"), spec.get("name"), str(exc)))
            continue
        if ch is None:
            raise ValueError(f"specs run past channel {layout.NUM_REGULAR}")
        if ch.enabled:
            notes = [*notes, f"overwrote occupied channel {channel}"]
        planned.append((ch, rec))
        applied.append(Applied(channel, rec.name or "", float(hz_to_mhz(rec.rx_hz)),
                               str(rec.shift), rec.mode, notes))
        channel += 1
    _write_all(planned)
    save_image(img, out)
    return ApplyResult(applied, skipped, out)


def _load_all(path: str, command: str) -> CloneImage:
    img = load_image(path)
    if not isinstance(img, CloneImage):
        raise ValueError(f"{command} needs an ALL backup, got a {img.kind} backup")
    return img


def extract(path: str, kind: str, out: str) -> str:
    """Write the MEMORY or SETUP backup carried by the ALL image at PATH; return OUT."""
    choices = partial.partial_kinds()
    try:
        want = {k.value: k for k in choices}[kind.upper()]
    except KeyError:
        names = " or ".join(k.lower() for k in choices)
        raise ValueError(f"kind must be {names}, got {kind!r}") from None
    out = resolve_output(path, out, same_kind=False)
    clone = _load_all(path, "extract")
    save_image(clone.memory if want == Kind.MEMORY else clone.setup, out)
    return out


def merge(base: str, out: str | None, *, memory: str | None = None,
          setup: str | None = None, in_place: bool = False) -> str:
    """Overlay MEMORY and/or SETUP backups onto the ALL image BASE (spec 2b,
    owner-masked); save to OUT. A partial is never a valid OUT. Returns OUT."""
    if memory is None and setup is None:
        raise ValueError(MERGE_NEEDS_PARTIAL)
    out = resolve_output(base, out, others=[p for p in (memory, setup) if p],
                         in_place=in_place)
    clone = _load_all(base, "merge")
    clone.merge(memory=MemoryImage.from_bytes(_read(memory)) if memory else None,
                setup=SetupImage.from_bytes(_read(setup)) if setup else None)
    save_image(clone, out)
    return out
