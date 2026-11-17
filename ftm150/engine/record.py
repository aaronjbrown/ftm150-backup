from dataclasses import dataclass

from . import layout, tables
from .fields import (
    Code,
    Flag,
    Freq,
    Indexed,
    check_in_band,
    encode_freq,
    patch_bits,
)
from .tables import Band, RawCode, as_band

__all__ = ["FIELDS", "Channel", "ChannelRecord", "write_record"]


@dataclass(frozen=True)
class ChannelRecord:
    """Format-neutral snapshot of one memory record (engine units: int Hz).

    Undecoded codes are carried as RawCode. For the optional fields, None means
    "not carried": write_record leaves those bits untouched.
      name      None: no name tag (PMS/VFO/Home) or not carried
      offset_hz the stored offset (reported for every shift; it is real data)
      tx_hz     the split tx frequency; None unless shift == "split"
      ctcss_hz / dcs  None when the stored index is outside the table
    """

    enabled: bool
    name: str | None
    band: Band | RawCode
    rx_hz: int
    shift: str | RawCode
    offset_hz: int | None
    tx_hz: int | None
    mode: str
    narrow: bool
    tone_mode: str | RawCode
    ctcss_hz: float | None
    dcs: int | None
    step: float | RawCode
    power: str | RawCode
    skip: bool
    mgrp: bool
    clock_shift: bool
    user_ctcss_hz: int
    show_name: bool


class Channel:
    """A 16-byte memory record view over a shared buffer (see spec §7)."""

    # No instance dict: assigning an unknown or edge-only name (e.g. rx_mhz)
    # raises AttributeError instead of silently creating an attribute.
    __slots__ = ("_buf", "_nf", "_no", "_o", "number")

    def __init__(self, buf: bytearray, offset: int, name_offset: int | None = None,
                 name_flag_offset: int | None = None, number: int | None = None) -> None:
        self.number = number     # 1..layout.NUM_REGULAR for regular channels, else None
        self._buf = buf
        self._o = offset
        self._no = name_offset
        self._nf = name_flag_offset

    def _b(self, i: int) -> int:
        return self._buf[self._o + i]

    def _set(self, i: int, value: int) -> None:
        self._buf[self._o + i] = value & 0xFF

    @property
    def raw(self) -> bytes:
        return bytes(self._buf[self._o:self._o + 16])

    # rec[0]: bit 7 enabled, bit 5 skip, bit 3 memory group, bits 2-0 band
    enabled = Flag(0, 0x80)
    skip = Flag(0, 0x20)
    mgrp = Flag(0, 0x08)
    # rec[1]: bit 5 narrow, bit 4 AM (see mode), bits 2-0 shift
    narrow = Flag(1, 0x20)
    shift = Code(1, 0x07, 0, tables.SHIFT)
    # rec[2..4]: rx frequency, int Hz (BCD + fraction code)
    rx_hz = Freq(2)
    # rec[5]: high nibble tone mode, low nibble step
    tone_mode = Code(5, 0xf0, 4, tables.TONE_MODE)
    step_khz = Code(5, 0x0f, 0, tables.STEP_KHZ)
    # rec[6..8]: split tx frequency (read through tx_hz)
    _tx_freq = Freq(6)
    # rec[9]: bits 7-6 power, bits 5-0 CTCSS index
    power = Code(9, 0xc0, 6, tables.POWER)
    ctcss_hz = Indexed(9, 0x3f, tables.CTCSS_TABLE, "{value} Hz is not a standard CTCSS tone")
    # rec[10]: bit 7 clock shift, bits 6-0 DCS index
    clock_shift = Flag(10, 0x80)
    dcs = Indexed(10, 0x7f, tables.DCS_TABLE, "{value} is not a standard DCS code")
    # rec[11]: bit 7 = display name (1) / frequency (0); bits 4-0 = user CTCSS / 100 Hz;
    # bits 6-5 undecoded
    show_name = Flag(11, 0x80, doc=(
        "Memory display mode (rec[11] bit 7): True shows the channel name, "
        "False the frequency."))

    @property
    def name(self) -> str:
        if self._no is None:
            return ""
        raw = bytes(self._buf[self._no:self._no + 16])
        return raw.split(b"\xff")[0].decode("ascii", "replace")

    @name.setter
    def name(self, text: str) -> None:
        if self._no is None:
            raise ValueError("this record type has no name tag")
        encoded = text.encode("ascii")
        if text != self.name:           # equal: tag bytes stay verbatim
            if len(encoded) > layout.NAME_MAX:   # refused, never truncated
                raise ValueError(f"name longer than {layout.NAME_MAX} characters: {text!r}")
            self._buf[self._no:self._no + 16] = encoded + b"\xff" * (16 - len(encoded))
        if self._nf is not None:  # name-present word; ADMS-17 ignores the tag without it
            self._buf[self._nf:self._nf + 2] = b"\x00\x00" if encoded else b"\xff\xff"

    @staticmethod
    def _band_value(value: object) -> Band | RawCode:
        """A setter value as a band: a Band, a band name (case-insensitive) as
        that Band, RawCode(0..3) as its Band, RawCode(4..7) verbatim."""
        if isinstance(value, str) and value.strip().upper() in Band.__members__:
            return Band[value.strip().upper()]
        value = as_band(value)          # RawCode(0..3) is that decoded band: range-checked
        if isinstance(value, Band) or (isinstance(value, RawCode) and 0 <= value <= 7):
            return value
        raise ValueError(f"band: {value!r} not one of {', '.join(b.name for b in Band)}")

    _check_in_band = staticmethod(check_in_band)

    @property
    def band(self) -> Band | RawCode:
        code = self._b(0) & 0x07
        return Band(code) if code in Band._value2member_map_ else RawCode(code)

    @band.setter
    def band(self, value: Band | RawCode | str) -> None:
        band = self._band_value(value)
        if self.enabled:                # blank records hold no meaningful frequency
            self._check_in_band(band, self.rx_hz)
        patch_bits(self, 0, 0x07, int(band))

    def retune(self, band: Band | RawCode | str, rx_hz: int) -> None:
        """Set band and rx frequency (int Hz) together; validates both before writing."""
        band = self._band_value(band)
        self._check_in_band(band, rx_hz)
        b2, b3, b4 = encode_freq(rx_hz)     # grid check before any write
        patch_bits(self, 0, 0x07, int(band))
        self._set(2, b2)
        self._set(3, b3)
        self._set(4, b4)

    @property
    def mode(self) -> str:
        return "AM" if self._b(1) & tables.MODE_AM_BIT else "FM"

    @mode.setter
    def mode(self, value: str) -> None:
        patch_bits(self, 1, tables.MODE_AM_BIT, tables.MODE_AM_BIT if value == "AM" else 0)

    @property
    def user_ctcss_hz(self) -> int:
        return (self._b(11) & tables.USER_CTCSS_MASK) * 100

    @user_ctcss_hz.setter
    def user_ctcss_hz(self, hz: int) -> None:
        if hz == self.user_ctcss_hz:    # no-op keeps same-base round trips lossless
            return
        if hz % 100 or not (300 <= hz <= 3000):
            raise ValueError(f"user CTCSS {hz} Hz: must be 300-3000 Hz in 100 Hz steps")
        patch_bits(self, 11, tables.USER_CTCSS_MASK, hz // 100)

    # rec[13]: repeater offset in 50 kHz units. rec[12] is probably the high
    # byte of a u16 (spec §7); until confirmed, non-zero is refused on read and
    # a write clears it.
    _OFFSET_STEP_HZ = 50_000

    @property
    def offset_hz(self) -> int:
        if self._b(12):
            raise ValueError(f"undecoded offset high byte rec[12] = {self._b(12):02x} "
                             "(an offset of 12.80 MHz or more?)")
        return self._b(13) * self._OFFSET_STEP_HZ

    @offset_hz.setter
    def offset_hz(self, hz: int) -> None:
        step = self._OFFSET_STEP_HZ
        if isinstance(hz, bool) or not isinstance(hz, int):     # as encode_freq
            raise TypeError(f"offset must be int Hz, got {hz!r}")
        if hz % step or not (0 <= hz <= 255 * step):
            raise ValueError(f"offset {hz!r} Hz: must be 0-12.75 MHz in 50 kHz steps")
        self._set(12, 0)
        self._set(13, hz // step)

    @property
    def tx_hz(self) -> int:
        """The transmit frequency the shift implies. An undecoded (RawCode)
        shift raises ValueError rather than guessing."""
        shift = self.shift
        if isinstance(shift, RawCode):
            raise ValueError(f"tx frequency unknown: shift code {int(shift)} is undecoded")
        if shift == "split":
            return self._tx_freq
        if shift == "-RPT":
            return self.rx_hz - self.offset_hz
        if shift == "+RPT":
            return self.rx_hz + self.offset_hz
        return self.rx_hz

    @tx_hz.setter
    def tx_hz(self, hz: int) -> None:
        if self.shift != "split":
            raise ValueError("tx_mhz can only be set on split channels; use shift/offset_khz")
        self._tx_freq = hz

    def to_record(self) -> ChannelRecord:
        """Snapshot this record as a ChannelRecord (see its docstring for None)."""
        shift = self.shift
        return ChannelRecord(
            enabled=self.enabled,
            name=None if self._no is None else self.name,
            band=self.band,
            rx_hz=self.rx_hz,
            shift=shift,
            offset_hz=self.offset_hz,
            tx_hz=self._tx_freq if shift == "split" else None,
            mode=self.mode,
            narrow=self.narrow,
            tone_mode=self.tone_mode,
            ctcss_hz=self.ctcss_hz,
            dcs=self.dcs,
            step=self.step_khz,
            power=self.power,
            skip=self.skip,
            mgrp=self.mgrp,
            clock_shift=self.clock_shift,
            user_ctcss_hz=self.user_ctcss_hz,
            show_name=self.show_name,
        )


def write_record(ch: Channel, rec: ChannelRecord) -> None:
    """Write `rec` into `ch`, validating the whole record before any byte changes.

    Every setter runs against a scratch copy of the record's 16 bytes (plus its
    name tag and name-present word, if any); the real buffer is updated only if
    all of them succeed. Bits the record does not represent (rec[1] 0x40,
    rec[11] 0x60, bytes 14/15) are carried through unchanged. None-valued
    optional fields are skipped, preserving their bits.
    """
    buf, o, no, nf = ch._buf, ch._o, ch._no, ch._nf
    scratch = bytearray(buf[o:o + 16])
    s_no = s_nf = None
    if no is not None:
        s_no = len(scratch)
        scratch += buf[no:no + 16]
    if nf is not None:
        s_nf = len(scratch)
        scratch += buf[nf:nf + 2]
    s = Channel(scratch, 0, s_no, s_nf, ch.number)
    was_enabled = s.enabled             # read before any setter runs
    if rec.mode not in ("AM", "FM"):    # the mode setter maps anything non-AM to FM
        raise ValueError(f"mode must be AM or FM, got {rec.mode!r}")

    s.enabled = rec.enabled
    # Unchanged name: skip the setter, so a blank, odd or longer stored tag round-trips verbatim.
    if rec.name is not None and s.name != rec.name:
        s.name = rec.name
    band = s.band
    rec_band = as_band(rec.band)        # RawCode(0..3) compares as its Band
    # Equal-value no-op: unchanged band+rx is not re-validated, so a
    # disabled/blank record round-trips. Types must match too (Band vs RawCode).
    # Enabling a disabled record always validates its band+rx.
    unchanged = (type(rec_band) is type(band) and rec_band == band
                 and type(rec.rx_hz) is int and rec.rx_hz == s.rx_hz)
    if not unchanged or (rec.enabled and not was_enabled):
        s.retune(rec_band, rec.rx_hz)
    s.shift = rec.shift                 # before tx: the tx setter requires split
    if rec.offset_hz is not None:
        s.offset_hz = rec.offset_hz
    if rec.tx_hz is not None:
        s.tx_hz = rec.tx_hz
    s.mode = rec.mode
    s.narrow = rec.narrow
    s.tone_mode = rec.tone_mode
    s.ctcss_hz = rec.ctcss_hz           # Indexed: None preserves the bits
    s.dcs = rec.dcs
    s.step_khz = rec.step
    s.power = rec.power
    s.skip = rec.skip
    s.mgrp = rec.mgrp
    s.clock_shift = rec.clock_shift
    s.user_ctcss_hz = rec.user_ctcss_hz
    s.show_name = rec.show_name

    buf[o:o + 16] = scratch[0:16]
    if no is not None and s_no is not None:
        buf[no:no + 16] = scratch[s_no:s_no + 16]
    if nf is not None and s_nf is not None:
        buf[nf:nf + 2] = scratch[s_nf:s_nf + 2]


# The single list of settable Channel fields (engine units: frequencies in int
# Hz). Which fields are settable is engine knowledge; how text is parsed for
# them is not: coerce.PARSERS (keyed by exactly these names) and SETTABLE
# derive from it, plus the MHz/kHz edge aliases.
FIELDS: tuple[str, ...] = (
    "name", "band", "rx_hz", "tx_hz", "mode", "narrow", "shift", "tone_mode",
    "step_khz", "power", "ctcss_hz", "dcs", "skip", "mgrp", "clock_shift",
    "user_ctcss_hz", "offset_hz", "enabled", "show_name",
)
