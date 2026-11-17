from . import layout

# Operating Manual, 28 APO: 0.5-2.0 h in 0.5 h steps, then 1 h steps to 12 h;
# the byte counts half-hours
APO_STEPS = {0: "OFF", **{h: f"{h / 2:.1f}h" for h in (1, 2, 3, 4, *range(6, 25, 2))}}
# Operating Manual, 44 SCAN RESUME
SCAN_RESUME = {0: "BUSY", 1: "HOLD", 2: "1SEC", 3: "3SEC", 4: "5SEC"}


class Settings:
    def __init__(self, buf: bytearray) -> None:
        self._buf = buf

    @property
    def apo(self) -> str | int:
        return APO_STEPS.get(self._buf[layout.APO_OFFSET], self._buf[layout.APO_OFFSET])

    @property
    def scan_resume_a(self) -> str | int:
        return SCAN_RESUME.get(self._buf[layout.SCAN_RESUME_A_OFFSET],
                               self._buf[layout.SCAN_RESUME_A_OFFSET])

    @property
    def scan_resume_b(self) -> str | int:
        return SCAN_RESUME.get(self._buf[layout.SCAN_RESUME_B_OFFSET],
                               self._buf[layout.SCAN_RESUME_B_OFFSET])
