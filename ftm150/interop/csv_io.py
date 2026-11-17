"""Native CSV I/O: pure row <-> ChannelRecord converters (file I/O is in ops).

Same-base import is byte-identical; cross-base import is lossless for all decoded
fields (the undecoded rec[1] 0x40 flag is not represented and defaults on a fresh
base).
"""
from ..engine.record import ChannelRecord
from ..engine.tables import Band, RawCode, as_band
from ..units import hz_to_mhz_text, mhz_to_hz, parse_step
from ._common import DUPLEX, DUPLEX_INV, TONE, TONE_INV, offset_text

CSV_COLUMNS = [
    "Location", "Name", "Frequency", "Duplex", "Offset", "Tone",
    "rToneFreq", "cToneFreq", "DtcsCode", "Mode", "TStep", "Skip",
    "Band", "TxPower", "Narrow", "MGrp", "ClockShift", "UserCTCSS", "ShowName",
]

_MODES = ("AM", "FM")


def _label(table: dict[str, str], code: str | RawCode) -> str:
    return str(code) if isinstance(code, RawCode) else table[code]


def _inv(table: dict[str, str], text: str, what: str) -> str | RawCode:
    text = str(text).strip()
    if text.isdigit():
        return RawCode(text)
    if text not in table:
        raise ValueError(
            f"{what}: {text!r} not one of {', '.join(repr(k) for k in table)}")
    return table[text]


def _blank(value: object) -> bool:
    return value is None or str(value).strip() in ("", "None")


def record_to_row(n: int, rec: ChannelRecord) -> dict[str, object]:
    """CH n's record as a native CSV row. Raw codes are written as their digits;
    a raw step code cannot be (TStep is a kHz number) and raises ValueError.

    Values keep their types (int Location/flags, float tones, str text), not all
    str: `dump --json` and the MCP dump_channels tool serialise these rows
    directly, and csv.DictWriter writes each via str()."""
    step = rec.step
    if isinstance(step, RawCode):
        raise ValueError(f"CH{n}: unknown step code {int(step)}; cannot export to CSV")
    band = rec.band
    return {
        "Location": n,
        "Name": rec.name if rec.name is not None else "",
        "Frequency": hz_to_mhz_text(rec.rx_hz),
        "Duplex": _label(DUPLEX, rec.shift),
        "Offset": offset_text(n, rec),
        "Tone": _label(TONE, rec.tone_mode),
        "rToneFreq": rec.ctcss_hz if rec.ctcss_hz is not None else "",
        "cToneFreq": rec.ctcss_hz if rec.ctcss_hz is not None else "",
        "DtcsCode": rec.dcs if rec.dcs is not None else "",
        "Mode": rec.mode,
        "TStep": step,
        "Skip": int(rec.skip),
        "Band": band.name if isinstance(band, Band) else str(band),
        "TxPower": str(rec.power),
        "Narrow": int(rec.narrow),
        "MGrp": int(rec.mgrp),
        "ClockShift": int(rec.clock_shift),
        "UserCTCSS": rec.user_ctcss_hz,
        "ShowName": int(rec.show_name),
    }


def _int(row: dict[str, str], col: str) -> int:
    return int(str(row[col]).strip())


def row_to_record(row: dict[str, str], *, show_name_default: bool) -> ChannelRecord:
    """A native CSV row as an (enabled) ChannelRecord. Pure: nothing is validated
    against an image here; write_record validates the whole record.

    Edge text is normalised (whitespace stripped, Mode upper-cased); Name is
    content and is kept verbatim. Not carried (None, so write_record keeps the
    target's bits): blank rToneFreq / DtcsCode, offset_hz on a split row, tx_hz
    on a non-split row. A blank or missing ShowName (pre-ShowName CSVs) takes
    `show_name_default`; import_csv passes the target's current value.
    """
    band_text = str(row["Band"]).strip()
    band: Band | RawCode = (as_band(RawCode(band_text)) if band_text.isdigit()
                            else Band[band_text])
    shift = _inv(DUPLEX_INV, row["Duplex"], "Duplex")
    offset_hz = tx_hz = None
    if shift == "split":
        tx_hz = mhz_to_hz(row["Offset"])          # split: Offset holds the tx MHz
    else:
        offset_hz = mhz_to_hz(row["Offset"])      # Offset is in MHz ("0.600")
    mode = str(row["Mode"]).strip().upper()
    if mode not in _MODES:
        raise ValueError(f"Mode: {row['Mode']!r} not one of 'AM', 'FM'")
    power_text = str(row["TxPower"]).strip()
    power: str | RawCode = RawCode(power_text) if power_text.isdigit() else power_text
    return ChannelRecord(
        enabled=True,
        name=row["Name"],
        band=band,
        rx_hz=mhz_to_hz(row["Frequency"]),
        shift=shift,
        offset_hz=offset_hz,
        tx_hz=tx_hz,
        mode=mode,
        narrow=bool(_int(row, "Narrow")),
        tone_mode=_inv(TONE_INV, row["Tone"], "Tone"),
        ctcss_hz=None if _blank(row.get("rToneFreq")) else float(row["rToneFreq"]),
        dcs=None if _blank(row.get("DtcsCode")) else _int(row, "DtcsCode"),
        step=parse_step(row["TStep"]),
        power=power,
        skip=bool(_int(row, "Skip")),
        mgrp=bool(_int(row, "MGrp")),
        clock_shift=bool(_int(row, "ClockShift")),
        user_ctcss_hz=_int(row, "UserCTCSS"),
        show_name=(show_name_default if _blank(row.get("ShowName"))
                   else bool(_int(row, "ShowName"))),
    )
