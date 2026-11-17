"""Exact unit conversion at the edges: decimal MHz/kHz text <-> integer Hz.

The engine holds frequencies as int Hz. Every external format (CSV text, CLI/MCP
field names, RepeaterSpec) stays in MHz/kHz and is converted here with
`decimal`, never float, so "146.65", "146.6500" and " 146.65 " all give the
same Hz and nothing is silently rounded. Stdlib only; imports nothing from the
engine.
"""
from decimal import Decimal, InvalidOperation

_MHZ = 6    # decimal exponent: Hz per MHz = 10**6
_KHZ = 3
_MAX_DIGITS = 30    # refuse absurd magnitudes (>= 10**30 Hz) before expanding them
_MAX_TEXT = 64      # DoS guard: longest accepted input text
_MAX_EXP = 64       # DoS guard: largest accepted |decimal exponent|, checked for
                    # every value (zero too) before any 10**n is built


def _to_hz(value: str | int | float | Decimal, exp: int, unit: str) -> int:
    text = str(value).strip()
    if len(text) > _MAX_TEXT:
        raise ValueError(f"{text[:20]!r}... ({len(text)} chars) is out of range for {unit}")
    try:
        d = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"{value!r} is not a number of {unit}") from None
    if not d.is_finite():
        raise ValueError(f"{value!r} is not a number of {unit}")
    sign, digits, e = d.as_tuple()
    assert isinstance(e, int)            # finite
    if abs(e) > _MAX_EXP or (d and d.adjusted() + exp >= _MAX_DIGITS):
        raise ValueError(f"{value!r} {unit} is out of range")
    # Exact on the digit tuple, not Decimal arithmetic (which rounds at the
    # context precision): Hz = digits * 10**(exponent + exp).
    scaled = e + exp
    hz: int
    if scaled >= 0:
        hz = int("".join(map(str, digits))) * 10 ** scaled
    else:
        whole, frac = digits[:scaled], digits[scaled:]
        if any(frac):
            raise ValueError(f"{value!r} {unit} is not a whole number of Hz")
        hz = int("".join(map(str, whole)) or "0")
    return -hz if sign else hz           # -0 -> 0


def mhz_to_hz(value: str | int | float | Decimal) -> int:
    """Exact MHz (text or number) -> int Hz. ValueError if not numeric, sub-Hz,
    or out of range (text > 64 chars, |exponent| > 64 -- zeros included -- or
    >= 10**30 Hz)."""
    return _to_hz(value, _MHZ, "MHz")


def khz_to_hz(value: str | int | float | Decimal) -> int:
    """Exact kHz (text or number) -> int Hz; same rules as mhz_to_hz."""
    return _to_hz(value, _KHZ, "kHz")


def hz_to_mhz(hz: int) -> Decimal:
    """Exact MHz value of `hz`."""
    return Decimal(hz).scaleb(-_MHZ)


def hz_to_mhz_text(hz: int) -> str:
    """MHz text with trailing zeros (and a bare dot) stripped: 146650000 ->
    "146.65". Exact for every Hz value; equal to 4-decimal text with
    trailing zeros stripped for anything on a 100 Hz grid, which every
    decoded FTM-150 frequency (2.5 kHz grid) is."""
    return f"{hz_to_mhz(hz):f}".rstrip("0").rstrip(".")


def hz_to_mhz_fixed3(hz: int) -> str:
    """MHz text with exactly 3 decimals (the CSV `Offset` text for
    non-split rows): 600000 -> "0.600". Refuses values finer than 1 kHz
    rather than rounding them."""
    if hz % 1000:
        raise ValueError(f"{hz} Hz is not a whole number of kHz")
    return f"{hz_to_mhz(hz):.3f}"


def parse_step(v: str) -> float:
    """A kHz number -> float (so "7" -> 7.0, which the setter rejects; "AUTO"
    raises ValueError: a memory channel has no AUTO step). Text input never
    yields a raw step code."""
    try:
        return float(v)
    except ValueError:
        raise ValueError(f"step must be a number of kHz, not {v!r}; "
                         "a memory channel has no AUTO step") from None
