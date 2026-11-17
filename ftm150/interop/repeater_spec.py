"""Translate neutral RepeaterSpec rows into FTM-150 channel edits (stdlib only)."""
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Required, TypedDict

from ..engine import layout
from ..engine.fields import FREQ_GRID_HZ
from ..engine.record import ChannelRecord
from ..engine.tables import BAND_RANGES, CTCSS_TABLE, DCS_TABLE, Band, RawCode
from ..units import hz_to_mhz_text, mhz_to_hz


class UnrepresentableError(Exception):
    """A RepeaterSpec that the FTM-150 format cannot encode."""


class ToneFields(TypedDict, total=False):
    """derive_tone's tone values: ctcss_hz for TONE/TSQL, dcs for DCS, neither
    for OFF. Value types are ChannelRecord's."""

    ctcss_hz: float | None
    dcs: int | None


class SpecFields(TypedDict, total=False):
    """spec_to_fields's ChannelRecord field values (value types are
    ChannelRecord's). offset_hz only for +/-RPT, tx_hz only for split,
    ctcss_hz / dcs only when the tone mode sets them."""

    band: Required[Band | RawCode]
    rx_hz: Required[int]
    shift: Required[str | RawCode]
    mode: Required[str]
    tone_mode: Required[str | RawCode]
    name: Required[str | None]
    narrow: Required[bool]
    offset_hz: int | None
    tx_hz: int | None
    ctcss_hz: float | None
    dcs: int | None


def derive_band(rx_hz: int) -> Band:
    for b in Band:
        lo, hi = BAND_RANGES[b]
        if lo <= rx_hz <= hi:
            return b
    raise UnrepresentableError(f"{hz_to_mhz_text(rx_hz)} MHz: no supported FTM-150 band")


_OFFSET_STEP_HZ = 50_000
_MAX_OFFSET_HZ = 255 * _OFFSET_STEP_HZ  # offset is stored as rec[13] * 50 kHz (one byte)


def derive_shift_offset(rx_hz: int, tx_hz: int) -> tuple[str, int | None, int | None]:
    if tx_hz == rx_hz:
        return ("simplex", None, None)
    offset_hz = abs(tx_hz - rx_hz)
    if offset_hz % _OFFSET_STEP_HZ != 0 or offset_hz > _MAX_OFFSET_HZ:
        return ("split", None, tx_hz)
    return ("+RPT" if tx_hz > rx_hz else "-RPT", offset_hz, None)


def _dcs_code(raw: object) -> int:
    """Producer DCS string -> code. Producer strips the leading "D", leaving
    e.g. "023", "023N" (normal) or "023I" (inverted polarity)."""
    s = str(raw).strip().upper()
    if s.startswith("D"):
        s = s[1:]
    digits, suffix = s.rstrip("NI"), s[len(s.rstrip("NI")):]
    if suffix == "I":
        raise UnrepresentableError(f"DCS {raw}: inverted polarity (FTM-150 DCS "
                                   "polarity storage not decoded)")
    if suffix not in ("", "N") or not digits.isdigit():
        raise UnrepresentableError(f"DCS {raw}: unrecognised code format")
    code = int(digits)
    if code not in DCS_TABLE:
        raise UnrepresentableError(f"DCS {raw}: not a standard code")
    return code


def _spec_hz(value: object, what: str) -> int:
    """RepeaterSpec MHz (decimal string or number) -> int Hz, exactly."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise UnrepresentableError(f"{what}: not a frequency in MHz: {value!r}")
    try:
        return mhz_to_hz(value)
    except ValueError as exc:
        raise UnrepresentableError(f"{what}: {exc}") from None


def _on_grid(hz: int, what: str) -> None:
    if hz % FREQ_GRID_HZ:
        raise UnrepresentableError(
            f"{what} {hz_to_mhz_text(hz)} MHz: not on the FTM-150's 2.5 kHz frequency grid")


def _tone_hz(value: object, what: str) -> float | None:
    """A spec CTCSS field (number or numeric text) as float Hz; None if absent."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise UnrepresentableError(f"{what}: not a tone frequency: {value!r}")
    try:
        return float(value)
    except ValueError:
        raise UnrepresentableError(f"{what}: not a tone frequency: {value!r}") from None


def derive_tone(ctcss_tx: object, ctcss_rx: object,
                dcs_tx: object, dcs_rx: object = None) -> tuple[str, ToneFields, list[str]]:
    """Collapse uplink/downlink CTCSS + DCS into one FTM-150 tone mode.

    The FTM-150's only confirmed DCS mode encodes and decodes one code, so
    DCS needs a single code; a one-sided code is applied with a note.
    """
    notes: list[str] = []
    if dcs_tx is not None or dcs_rx is not None:
        tx_code = _dcs_code(dcs_tx) if dcs_tx is not None else None
        rx_code = _dcs_code(dcs_rx) if dcs_rx is not None else None
        if tx_code is not None and rx_code is not None and tx_code != rx_code:
            raise UnrepresentableError(
                f"DCS tx {dcs_tx} / rx {dcs_rx}: FTM-150 holds one DCS code")
        code = tx_code if tx_code is not None else rx_code
        if rx_code is None:
            notes.append(f"tx-only DCS {code:03d} applied as DCS (radio will also "
                         f"squelch on {code:03d}; FTM-150 has no encode-only DCS)")
        elif tx_code is None:
            notes.append(f"rx-only DCS {code:03d} applied as DCS (also transmitted)")
        dropped = [str(t) for t in (ctcss_tx, ctcss_rx) if t is not None]
        if dropped:
            notes.append(f"CTCSS {'/'.join(dropped)} dropped in favour of DCS")
        return ("DCS", {"dcs": code}, notes)
    tx = _tone_hz(ctcss_tx, "ctcss_tx_hz")
    rx = _tone_hz(ctcss_rx, "ctcss_rx_hz")
    if tx is None and rx is None:
        return ("OFF", {}, notes)
    if tx is not None and rx is not None and tx == rx:
        if tx not in CTCSS_TABLE:
            raise UnrepresentableError(f"CTCSS {tx}: not a standard tone")
        return ("TSQL", {"ctcss_hz": tx}, notes)
    chosen = tx if tx is not None else rx
    if tx is not None and rx is not None and tx != rx:
        notes.append(f"rx tone {rx} dropped (FTM-150 holds one tone)")
    elif tx is None and rx is not None:
        notes.append(f"rx-only tone {rx} applied as TX tone")
    if chosen not in CTCSS_TABLE:
        raise UnrepresentableError(f"CTCSS {chosen}: not a standard tone")
    return ("TONE", {"ctcss_hz": chosen}, notes)


_DIGITAL_MODES = {"DMR", "DSTAR", "FUSION", "P25", "NXDN", "TETRA", "M17"}


def derive_narrow(params: Mapping[str, Any] | None) -> bool:
    """FM channel spacing from params.bandwidth_khz: <=12.5 kHz is narrow.

    Unknown or unparseable bandwidth keeps the wide default (fails safe for
    receive). A params
    value that is not an object is malformed: UnrepresentableError.
    """
    if params is not None and not isinstance(params, Mapping):
        raise UnrepresentableError(f"params: expected an object, got {type(params).__name__}")
    bw = (params or {}).get("bandwidth_khz")
    if bw is None:
        return False
    try:
        return float(bw) <= 12.5
    except (TypeError, ValueError):
        return False


def _text_field(spec: Mapping[str, Any], key: str) -> str | None:
    """An optional string field; a non-string value is malformed."""
    value = spec.get(key)
    if value is not None and not isinstance(value, str):
        raise UnrepresentableError(f"{key}: expected a string, got {type(value).__name__}")
    return value


def _required(spec: Mapping[str, Any], key: str) -> object:
    if spec.get(key) is None:
        raise UnrepresentableError(f"missing {key}")
    return spec[key]


def sanitize_name(spec: Mapping[str, Any]) -> tuple[str, list[str]]:
    name, callsign = _text_field(spec, "name"), _text_field(spec, "callsign")
    raw = name or callsign or ""
    clean = raw.encode("ascii", "ignore").decode("ascii")[:layout.NAME_MAX]
    notes = [] if clean == raw else [f"name {raw!r} adjusted to {clean!r}"]
    return clean, notes


def spec_to_fields(spec: Mapping[str, Any]) -> tuple[SpecFields, list[str]]:
    mode = _required(spec, "mode")
    if not isinstance(mode, str):
        raise UnrepresentableError(f"mode: expected a string, got {type(mode).__name__}")
    if mode in _DIGITAL_MODES:
        raise UnrepresentableError(f"{mode}: FTM-150 is FM-only")
    if mode != "FM":
        raise UnrepresentableError(f"{mode}: unsupported mode")
    rx = _spec_hz(_required(spec, "rx_frequency_mhz"), "rx")
    tx = _spec_hz(_required(spec, "tx_frequency_mhz"), "tx")
    _on_grid(rx, "rx")
    _on_grid(tx, "tx")
    band = derive_band(rx)
    lo, hi = BAND_RANGES[band]
    if not (lo <= tx <= hi):
        raise UnrepresentableError(f"tx {hz_to_mhz_text(tx)} MHz outside band {band.name} "
                                   f"of rx {hz_to_mhz_text(rx)} MHz")
    shift, offset_hz, tx_split = derive_shift_offset(rx, tx)
    dcs_tx = spec.get("dcs_tx_code")
    if dcs_tx is None:
        dcs_tx = spec.get("dcs_code")  # legacy producer field (pre-tx/rx split)
    tone_mode, tone_fields, notes = derive_tone(
        spec.get("ctcss_tx_hz"), spec.get("ctcss_rx_hz"),
        dcs_tx, spec.get("dcs_rx_code"))
    name, name_notes = sanitize_name(spec)
    fields: SpecFields = {"band": band, "rx_hz": rx, "shift": shift,
                          "mode": "FM", "tone_mode": tone_mode, "name": name,
                          "narrow": derive_narrow(spec.get("params"))}
    if offset_hz is not None:
        fields["offset_hz"] = offset_hz
    if tx_split is not None:
        fields["tx_hz"] = tx_split
    # Key by key: TypedDict.update() will not take the narrower ToneFields.
    if "ctcss_hz" in tone_fields:
        fields["ctcss_hz"] = tone_fields["ctcss_hz"]
    if "dcs" in tone_fields:
        fields["dcs"] = tone_fields["dcs"]
    return fields, notes + name_notes


def spec_to_record(spec: Mapping[str, Any], *,
                   user_ctcss_hz: int) -> tuple[ChannelRecord, list[str]]:
    """A RepeaterSpec as the ChannelRecord ops.apply_specs writes, plus notes. Pure.

    Fields the spec does not derive take the apply_specs policy: HIGH power,
    5 kHz step, skip/mgrp/clock_shift off, name displayed, enabled.
    `user_ctcss_hz` is the target's own value (passed through unchanged).
    Not carried (None: the target's bits are kept): offset_hz unless +/-RPT,
    tx_hz unless split, ctcss_hz/dcs unless the tone mode sets them.
    Raises UnrepresentableError as spec_to_fields does, including for a
    missing required field or a wrong-typed value.
    """
    try:
        fields, notes = spec_to_fields(spec)
    except TypeError as exc:    # backstop: any other wrong-typed value is malformed
        raise UnrepresentableError(f"malformed spec: {exc}") from None
    rec = ChannelRecord(
        enabled=True,
        name=fields["name"],
        band=fields["band"],
        rx_hz=fields["rx_hz"],
        shift=fields["shift"],
        offset_hz=fields.get("offset_hz"),
        tx_hz=fields.get("tx_hz"),
        mode=fields["mode"],
        narrow=fields["narrow"],
        tone_mode=fields["tone_mode"],
        ctcss_hz=fields.get("ctcss_hz"),
        dcs=fields.get("dcs"),
        step=5.0,
        power="HIGH",
        skip=False,
        mgrp=False,
        clock_shift=False,
        user_ctcss_hz=user_ctcss_hz,
        show_name=True,     # display the name, not the frequency (user preference)
    )
    return rec, notes


@dataclass
class Applied:
    channel: int
    name: str
    rx_mhz: float           # results stay MHz at the edge; the engine holds int Hz
    shift: str
    mode: str
    notes: list[str]


@dataclass
class Skipped:
    source_id: object
    name: object
    reason: str


@dataclass
class ApplyResult:
    applied: list[Applied]
    skipped: list[Skipped]
    out_path: object = None
