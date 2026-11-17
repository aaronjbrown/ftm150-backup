"""Declarative bit-field descriptors for 16-byte memory records (spec §7)."""
from collections.abc import Sequence
from typing import Any, Protocol, Self, Union, overload

from ..units import hz_to_mhz_text
from . import tables
from .tables import Band, RawCode

_BCD_LIMIT_HZ = 100_000 * 10_000    # 5 BCD digits of 10 kHz
FREQ_GRID_HZ = 2_500                # finest grid the confirmed fraction codes reach
_FRACTION_CODE = {hz: code for code, hz in tables.FREQ_FRACTION_HZ.items()}


def decode_freq(b2: int, b3: int, b4: int) -> int:
    """BCD frequency bytes -> int Hz: 5 BCD digits of 10 kHz plus the
    sub-10 kHz fraction code in the high nibble of b2 (spec §7). A fraction
    code outside tables.FREQ_FRACTION_HZ is refused, never read as another
    frequency."""
    digits = (b2 & 0xF, b3 >> 4, b3 & 0xF, b4 >> 4, b4 & 0xF)
    if max(digits) > 9:
        raise ValueError(f"non-BCD frequency nibble in {b2:02x} {b3:02x} {b4:02x}")
    code = b2 >> 4
    if code not in tables.FREQ_FRACTION_HZ:
        raise ValueError(f"undecoded frequency fraction code {code:X} in "
                         f"{b2:02x} {b3:02x} {b4:02x}")
    return int("".join(map(str, digits))) * 10_000 + tables.FREQ_FRACTION_HZ[code]


def encode_freq(hz: int) -> tuple[int, int, int]:
    """Return (b2, b3, b4): b2 = fraction code (high nibble) | top BCD digit
    (low nibble). The codec owns all of b2.

    The confirmed fraction codes resolve 2.5 kHz; anything finer is refused
    rather than floored to a different frequency, and anything outside the
    5 BCD digits is refused rather than wrapped."""
    if isinstance(hz, bool) or not isinstance(hz, int):
        raise TypeError(f"frequency must be int Hz, got {hz!r}")
    if hz % FREQ_GRID_HZ:
        raise ValueError(f"{hz_to_mhz_text(hz)} MHz is not on the FTM-150's 2.5 kHz "
                         "frequency grid")
    if not 0 <= hz < _BCD_LIMIT_HZ:
        raise ValueError(f"{hz_to_mhz_text(hz)} MHz is outside the 5-digit BCD frequency range")
    n, frac = divmod(hz, 10_000)        # 5 BCD digits = MHz*100
    code = _FRACTION_CODE[frac] << 4
    b2 = code | ((n // 10000) % 10)
    b3 = (((n // 1000) % 10) << 4) | ((n // 100) % 10)
    b4 = (((n // 10) % 10) << 4) | (n % 10)
    return b2, b3, b4


def check_in_band(band: Band | RawCode, hz: int) -> None:
    if isinstance(band, Band):          # range of an undecoded band is unknown: not guessed
        lo, hi = tables.BAND_RANGES[band]
        if not (lo <= hz <= hi):
            raise ValueError(f"{hz_to_mhz_text(hz)} MHz outside band {band.name} "
                             f"({hz_to_mhz_text(lo)}-{hz_to_mhz_text(hi)})")


def resolve_code(field: str, value: object, table: dict[int, Any],
                 inv: dict[Any, int], mask: int) -> int:
    """Resolve a setter value to a raw code: a RawCode within `mask` is written
    unchanged; any other value is a label validated against the table."""
    if isinstance(value, RawCode):
        if 0 <= value <= mask:
            return int(value)
        raise ValueError(f"{field}: {value!r} out of range 0..{mask}")
    if not isinstance(value, bool) and isinstance(value, (str, int, float)) and value in inv:
        return inv[value]
    labels = ", ".join(str(v) for v in table.values())
    raise ValueError(f"{field}: {value!r} not one of {labels}")


class RecordView(Protocol):
    """What a descriptor needs from its owner: a buffer and a record offset."""

    _buf: bytearray
    _o: int

    @property
    def band(self) -> Band | RawCode: ...


def _get(obj: RecordView, i: int) -> int:
    return obj._buf[obj._o + i]


def patch_bits(obj: RecordView, i: int, mask: int, value: int) -> None:
    """Set the bits under `mask` at rec[i] to `value` (already shifted)."""
    cur = obj._buf[obj._o + i]
    obj._buf[obj._o + i] = (cur & ~mask & 0xFF) | (value & mask)


class _Field[T, W]:
    name: str = "?"

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    @overload
    def __get__(self, obj: None, owner: type | None = None) -> Self: ...
    @overload
    def __get__(self, obj: RecordView, owner: type | None = None) -> T: ...
    def __get__(self, obj: RecordView | None, owner: type | None = None) -> Self | T:
        if obj is None:
            return self
        return self.read(obj)

    def __set__(self, obj: RecordView, value: W) -> None:
        self.write(obj, value)

    def read(self, obj: RecordView) -> T:
        raise NotImplementedError

    def write(self, obj: RecordView, value: W) -> None:
        raise NotImplementedError


class Flag(_Field[bool, object]):
    """A single-bit (or all-bits-of-mask) boolean at rec[byte]. ``doc``, if
    given, becomes this field's docstring (shown by help() on the owner)."""

    def __init__(self, byte: int, mask: int, doc: str | None = None) -> None:
        self.byte, self.mask = byte, mask
        if doc is not None:
            self.__doc__ = doc

    def read(self, obj: RecordView) -> bool:
        return bool(_get(obj, self.byte) & self.mask)

    def write(self, obj: RecordView, value: object) -> None:
        patch_bits(obj, self.byte, self.mask, self.mask if value else 0)


class Code[T: str | float](_Field[Union[T, RawCode], Union[T, RawCode]]):  # noqa: UP007 - `|` loses T at runtime
    """A table-coded field at (rec[byte] & mask) >> shift. Reads the table label,
    or RawCode(n) for an undecoded code; writes a label validated against the
    table, or a RawCode within the field's width verbatim."""

    def __init__(self, byte: int, mask: int, shift: int, table: dict[int, T]) -> None:
        self.byte, self.mask, self.shift = byte, mask, shift
        self.table: dict[int, T] = table
        self.inv: dict[T, int] = {v: k for k, v in table.items()}

    def read(self, obj: RecordView) -> T | RawCode:
        code = (_get(obj, self.byte) & self.mask) >> self.shift
        return self.table.get(code, RawCode(code))

    def write(self, obj: RecordView, value: T | RawCode) -> None:
        code = resolve_code(self.name, value, self.table, self.inv, self.mask >> self.shift)
        patch_bits(obj, self.byte, self.mask, code << self.shift)


class Indexed[T](_Field[Union[T, None], Union[T, None]]):  # noqa: UP007 - `|` loses T at runtime
    """An index into a value list at rec[byte] & mask. An index past the list
    reads as None; writing None preserves the bits (out-of-table, not guessed)."""

    def __init__(self, byte: int, mask: int, values: Sequence[T], error: str) -> None:
        self.byte, self.mask, self.values, self.error = byte, mask, values, error

    def read(self, obj: RecordView) -> T | None:
        idx = _get(obj, self.byte) & self.mask
        return self.values[idx] if idx < len(self.values) else None

    def write(self, obj: RecordView, value: T | None) -> None:
        if value is None:
            return
        if value not in self.values:
            raise ValueError(self.error.format(value=value))
        patch_bits(obj, self.byte, self.mask, self.values.index(value))


class Freq(_Field[int, int]):
    """A BCD frequency (int Hz) in rec[byte..byte+2] (spec §7), fraction code
    included. Writes are range-checked against the record's band when it is a
    decoded Band, and always checked against the 2.5 kHz grid."""

    def __init__(self, byte: int) -> None:
        self.byte = byte

    def read(self, obj: RecordView) -> int:
        i = self.byte
        return decode_freq(_get(obj, i), _get(obj, i + 1), _get(obj, i + 2))

    def write(self, obj: RecordView, value: int) -> None:
        check_in_band(obj.band, value)
        b2, b3, b4 = encode_freq(value)
        patch_bits(obj, self.byte, 0xff, b2)
        patch_bits(obj, self.byte + 1, 0xff, b3)
        patch_bits(obj, self.byte + 2, 0xff, b4)

