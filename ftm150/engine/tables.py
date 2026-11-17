from enum import IntEnum

CTCSS_TABLE = [
    67.0, 69.3, 71.9, 74.4, 77.0, 79.7, 82.5, 85.4, 88.5, 91.5,
    94.8, 97.4, 100.0, 103.5, 107.2, 110.9, 114.8, 118.8, 123.0, 127.3,
    131.8, 136.5, 141.3, 146.2, 151.4, 156.7, 159.8, 162.2, 165.5, 167.9,
    171.3, 173.8, 177.3, 179.9, 183.5, 186.2, 189.9, 192.8, 196.6, 199.5,
    203.5, 206.5, 210.7, 218.1, 225.7, 229.1, 233.6, 241.8, 250.3, 254.1,
]

DCS_TABLE = [
    23, 25, 26, 31, 32, 36, 43, 47, 51, 53, 54, 65, 71, 72, 73, 74,
    114, 115, 116, 122, 125, 131, 132, 134, 143, 145, 152, 155, 156, 162, 165, 172, 174,
    205, 223, 226, 243, 244, 245, 246, 251, 252, 255, 261, 263, 265, 266, 271, 274,
    306, 311, 315, 325, 331, 332, 343, 346, 351, 356, 364, 365, 371,
    411, 412, 413, 423, 431, 432, 445, 446, 452, 454, 455, 462, 464, 465, 466,
    503, 506, 516, 523, 526, 532, 546, 565,
    606, 612, 624, 627, 631, 632, 654, 662, 664,
    703, 712, 723, 731, 732, 734, 743, 754,
]


class Band(IntEnum):
    AIR = 0
    VHF = 1
    VHF_UHF = 2
    UHF = 3


class RawCode(int):
    """An undecoded field code, preserved verbatim."""

    def __repr__(self) -> str:
        return f"RawCode({int(self)})"

    def __str__(self) -> str:
        return str(int(self))


def as_band[T](value: T) -> Band | T:
    """A RawCode naming a decoded band (0-3) as that Band; anything else
    unchanged. RawCode is only for undecoded codes (4-7), whose range is
    unknown and so not checked; a decoded band is always range-checked."""
    if isinstance(value, RawCode) and value in Band._value2member_map_:
        return Band(value)
    return value


# Inclusive rx range per decoded band, in Hz.
BAND_RANGES: dict[Band, tuple[int, int]] = {
    Band.AIR: (108_000_000, 137_000_000),
    Band.VHF: (137_000_000, 174_000_000),
    Band.VHF_UHF: (174_000_000, 400_000_000),
    Band.UHF: (400_000_000, 550_000_000),
}

# rec[1]: bit 0x10 = AM (else FM); low 3 bits = shift
MODE_AM_BIT = 0x10
SHIFT = {0: "simplex", 2: "-RPT", 3: "+RPT", 4: "split"}
# rec[2] / rec[6] high nibble: sub-10 kHz fraction code -> Hz added to the BCD
# frequency. Confirmed codes only (spec §7); the firmware lists more (1.25 kHz
# and 1/3-kHz codes) that no capture has shown yet.
FREQ_FRACTION_HZ: dict[int, int] = {0x0: 0, 0x4: 2_500, 0x8: 5_000, 0xC: 7_500}
# rec[11] bits 4-0: user CTCSS / 100 Hz (the firmware masks with 0x1F)
USER_CTCSS_MASK = 0x1F
# rec[5]: high nibble tone mode, low nibble step
TONE_MODE = {0: "OFF", 1: "TONE", 2: "TSQL", 4: "DCS"}
# rec[9]: bits 7-6 power
POWER = {0: "HIGH", 1: "MED", 2: "LOW"}
# code 2 is never observed (candidate 8.33 kHz); it reads as RawCode(2)
STEP_KHZ: dict[int, float] = {
    0: 5.0, 1: 6.25, 3: 10.0, 4: 12.5, 5: 15.0,
    6: 20.0, 7: 25.0, 8: 50.0, 9: 100.0,
}
