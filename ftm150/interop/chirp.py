"""CHIRP CSV interop: pure ChannelRecord <-> CHIRP row converters.

CHIRP rows are built from, and parsed into, ChannelRecord values directly; the
native CSV row format is not involved.
"""
from typing import TypedDict

from ..engine.record import ChannelRecord
from ..engine.tables import Band, RawCode
from ..units import hz_to_mhz_text, mhz_to_hz, parse_step
from ._common import DUPLEX, DUPLEX_INV, TONE, TONE_INV, offset_text
from .repeater_spec import UnrepresentableError, derive_band

CHIRP_COLUMNS = [
    "Location", "Name", "Frequency", "Duplex", "Offset", "Tone",
    "rToneFreq", "cToneFreq", "DtcsCode", "DtcsPolarity", "Mode", "TStep",
    "Skip", "Comment",
]


class ChirpDefaults(TypedDict):
    """The ChannelRecord fields CHIRP lacks (value types are ChannelRecord's)."""

    power: str | RawCode
    mgrp: bool
    clock_shift: bool
    user_ctcss_hz: int


class ChirpFields(TypedDict):
    """chirp_to_fields's ChannelRecord field values (value types are
    ChannelRecord's). Every key is always present; see chirp_to_fields."""

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
    skip: bool


# Documented defaults for the ChannelRecord fields CHIRP lacks (the
# empty-target-only policy lives in ops). show_name and enabled are not here:
# they are the caller's to merge.
CHIRP_DEFAULTS: ChirpDefaults = {
    "power": "HIGH", "mgrp": False, "clock_shift": False, "user_ctcss_hz": 1500,
}

_MODES = ("FM", "NFM", "AM")
# The CHIRP column holding the tone value each tone mode uses.
_TONE_VALUE_COL = {"TONE": "rToneFreq", "TSQL": "cToneFreq", "DCS": "DtcsCode"}


def _refuse_raw(n: int, rec: ChannelRecord) -> None:
    for what, value in (("band", rec.band), ("shift", rec.shift),
                        ("tone mode", rec.tone_mode), ("step", rec.step),
                        ("power", rec.power)):
        if isinstance(value, RawCode):
            raise ValueError(f"CH{n}: {what} {int(value)} is a raw/unknown code; "
                             f"CHIRP cannot represent it")


def record_to_chirp(n: int, rec: ChannelRecord) -> dict[str, str]:
    """CH n's record as a CHIRP row. Any raw (undecoded) code raises ValueError."""
    _refuse_raw(n, rec)
    assert isinstance(rec.shift, str) and isinstance(rec.tone_mode, str)
    tone = "" if rec.ctcss_hz is None else str(rec.ctcss_hz)
    return {
        "Location": str(n),
        "Name": rec.name if rec.name is not None else "",
        "Frequency": hz_to_mhz_text(rec.rx_hz),
        "Duplex": DUPLEX[rec.shift],
        "Offset": offset_text(n, rec),
        "Tone": TONE[rec.tone_mode],
        "rToneFreq": tone,
        "cToneFreq": tone,
        "DtcsCode": "" if rec.dcs is None else str(rec.dcs),
        "DtcsPolarity": "NN",
        "Mode": "NFM" if rec.narrow else rec.mode,
        "TStep": str(rec.step),
        "Skip": "S" if rec.skip else "",
        "Comment": "",
    }


def _skip(loc: str, row: dict[str, str]) -> bool:
    skip = str(row.get("Skip", "")).strip()
    if skip == "":
        return False
    if skip == "S":
        return True
    raise ValueError(f"CH{loc}: Skip {skip!r} not supported (only '' or 'S')")


def _code(loc: str, row: dict[str, str], col: str, table: dict[str, str]) -> str:
    text = str(row.get(col, "")).strip()
    if text not in table:
        raise ValueError(f"CH{loc}: {col} {text!r} not one of "
                         f"{', '.join(repr(k) for k in table)}")
    return table[text]


def chirp_to_fields(row: dict[str, str]) -> tuple[int, ChirpFields]:
    """Parse one CHIRP row into (channel number, the ChannelRecord field values
    CHIRP carries). Pure; fields CHIRP lacks (power, mgrp, clock_shift,
    user_ctcss_hz, show_name, enabled) are absent -- see CHIRP_DEFAULTS.

    offset_hz / tx_hz are both present, the one the row does not carry as None
    (so a merged record never keeps a stale split tx or offset). ctcss_hz / dcs
    are None (not carried) unless the Tone mode uses them; a Tone mode whose
    value column (rToneFreq / cToneFreq / DtcsCode) is blank raises.
    """
    loc = str(row.get("Location", "")).strip()
    try:
        n = int(loc)
    except ValueError:
        raise ValueError(f"Location {loc!r} is not a channel number") from None
    if str(row.get("DtcsPolarity", "NN")).strip() not in ("NN", ""):
        raise ValueError(
            f"CH{loc}: DtcsPolarity {row['DtcsPolarity']!r} not supported "
            f"(FTM-150 DCS is normal polarity only)")
    mode = str(row.get("Mode", "")).strip().upper()
    if mode not in _MODES:
        raise ValueError(f"CH{loc}: Mode {mode!r} not one of 'FM', 'NFM', 'AM'")
    shift = _code(loc, row, "Duplex", DUPLEX_INV)
    tone_mode = _code(loc, row, "Tone", TONE_INV)
    try:
        rx_hz = mhz_to_hz(row["Frequency"])
        band: Band = derive_band(rx_hz)
        offset = mhz_to_hz(row.get("Offset", ""))
        step = parse_step(row.get("TStep", ""))
        ctcss_hz: float | None = None
        dcs: int | None = None
        col = _TONE_VALUE_COL.get(tone_mode)
        if col is not None:
            value = str(row.get(col) or "").strip()
            if not value:
                raise ValueError(f"Tone mode {TONE[tone_mode]!r} needs {col}")
            if tone_mode == "DCS":
                dcs = int(value)
            else:
                ctcss_hz = float(value)
    except (UnrepresentableError, ValueError, KeyError) as e:
        raise ValueError(f"CH{loc}: {e}") from None
    split = shift == "split"
    return n, {
        "name": row.get("Name", ""),
        "band": band,
        "rx_hz": rx_hz,
        "shift": shift,
        "offset_hz": None if split else offset,
        "tx_hz": offset if split else None,
        "mode": "AM" if mode == "AM" else "FM",
        "narrow": mode == "NFM",
        "tone_mode": tone_mode,
        "ctcss_hz": ctcss_hz,
        "dcs": dcs,
        "step": step,
        "skip": _skip(loc, row),
    }
