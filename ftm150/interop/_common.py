"""Format-neutral helpers shared by the native CSV and CHIRP adapters.

Both formats use the same Duplex / Tone column labels and the same Offset text
rule; neither adapter depends on the other's row code.
"""
from ..engine.record import ChannelRecord
from ..units import hz_to_mhz_fixed3, hz_to_mhz_text

# ChannelRecord.shift -> Duplex column text, and back.
DUPLEX = {"simplex": "", "-RPT": "-", "+RPT": "+", "split": "split"}
DUPLEX_INV = {v: k for k, v in DUPLEX.items()}
# ChannelRecord.tone_mode -> Tone column text, and back.
TONE = {"OFF": "", "TONE": "Tone", "TSQL": "TSQL", "DCS": "DTCS"}
TONE_INV = {v: k for k, v in TONE.items()}


def offset_text(n: int, rec: ChannelRecord) -> str:
    """The Offset column for CH n: the tx MHz on a split record ("147.25"),
    otherwise the offset in MHz with 3 decimals ("0.600")."""
    if rec.shift == "split":
        if rec.tx_hz is None:
            raise ValueError(f"CH{n}: split record carries no tx frequency")
        return hz_to_mhz_text(rec.tx_hz)
    if rec.offset_hz is None:
        raise ValueError(f"CH{n}: record carries no offset")
    return hz_to_mhz_fixed3(rec.offset_hz)
