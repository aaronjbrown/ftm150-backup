"""String -> typed value coercion for settable Channel fields (shared by CLI + MCP).

The engine says WHICH fields are settable (engine.record.FIELDS); this module
says HOW their text is parsed (PARSERS, keyed by exactly those names). SETTABLE
derives from PARSERS plus EDGE_ALIASES: the user-facing MHz/kHz names for the
engine's int-Hz fields, converted exactly (decimal) by ftm150.units."""
from collections.abc import Callable
from decimal import Decimal

from .engine import tables
from .engine.record import FIELDS
from .engine.tables import Band, RawCode
from .units import hz_to_mhz, khz_to_hz, mhz_to_hz, parse_step

# --- text parsers for settable fields (CLI / MCP edge) -----------------------

def parse_bool(v: str) -> bool:
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"expected a boolean, got {v!r}")


def parse_band(v: str) -> Band | RawCode:
    s = str(v).strip()
    if s.isdigit():
        return tables.as_band(RawCode(int(s)))     # 0-3 -> Band; 4-7 stay raw
    return Band[s.upper()]


def parse_code(v: str) -> RawCode | str:
    """Digit string -> RawCode; otherwise the upper-cased label.
    Parses only; the Channel setter validates against the table."""
    s = str(v).strip()
    return RawCode(s) if s.isdigit() else s.upper()


def parse_shift(v: str) -> RawCode | str:
    s = str(v).strip()
    return RawCode(s) if s.isdigit() else s


def parse_mode(v: str) -> str:
    s = str(v).strip().upper()
    if s not in ("AM", "FM"):
        raise ValueError(f"mode must be AM or FM, got {v!r}")
    return s


# Engine field name -> text parser; keyed by exactly engine.record.FIELDS
# (asserted by test_fields_registry_is_single_source).
PARSERS: dict[str, Callable[[str], object]] = {
    "name": str,
    "band": parse_band,
    "rx_hz": int,
    "tx_hz": int,
    "mode": parse_mode,
    "narrow": parse_bool,
    "shift": parse_shift,
    "tone_mode": parse_code,
    "step_khz": parse_step,
    "power": parse_code,
    "ctcss_hz": float,
    "dcs": int,
    "skip": parse_bool,
    "mgrp": parse_bool,
    "clock_shift": parse_bool,
    "user_ctcss_hz": int,
    "offset_hz": int,
    "enabled": parse_bool,
    "show_name": parse_bool,
}

# Edge-only field name -> (engine field, exact text -> int Hz parser).
EDGE_ALIASES: dict[str, tuple[str, Callable[[str], int]]] = {
    "rx_mhz": ("rx_hz", mhz_to_hz),
    "tx_mhz": ("tx_hz", mhz_to_hz),
    "offset_khz": ("offset_hz", khz_to_hz),
}

# User-facing settable names: FIELDS minus the int-Hz engine names (internal
# only), plus their MHz/kHz edge aliases.
_ALIAS_TARGETS = {target for target, _ in EDGE_ALIASES.values()}
SETTABLE: dict[str, Callable[[str], object]] = {
    **{name: PARSERS[name] for name in FIELDS if name not in _ALIAS_TARGETS},
    **{name: parse for name, (_, parse) in EDGE_ALIASES.items()}}


def coerce(field: str, value: str) -> tuple[str, object]:
    """Parse `value` for `field`; return (engine field to set, parsed value)."""
    if field not in SETTABLE:
        raise KeyError(
            f"unknown field {field!r}; settable: {', '.join(sorted(SETTABLE))}")
    engine_field = EDGE_ALIASES[field][0] if field in EDGE_ALIASES else field
    return engine_field, SETTABLE[field](value)


def display(field: str, value: object) -> str:
    """User-facing text of a value coerced for `field`, in that field's own
    units (an aliased MHz/kHz name shows MHz/kHz, not the engine's Hz)."""
    if field in ("rx_mhz", "tx_mhz") and isinstance(value, int):
        return str(float(hz_to_mhz(value)))     # str of the parsed MHz as a float
    if field == "offset_khz" and isinstance(value, int):
        return f"{Decimal(value).scaleb(-3):f}".rstrip("0").rstrip(".")  # e.g. "600"
    return str(value)
