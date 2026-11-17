from ftm150 import Band, CloneImage
from ftm150.engine import layout
from tests.files import ALL_A, ALL_B, load


def test_regular_channels_1_based():
    img = load(CloneImage, ALL_A)
    assert len(img.memory.channels) == 999
    assert img.memory.channels[1].name == "RPT2M-A"
    assert [c.name for c in img.memory.channels][:2] == ["RPT2M-A", "RPT2M-B"]


def test_pms_pairs():
    img = load(CloneImage, ALL_B)
    assert len(img.memory.pms) == 50
    assert img.memory.pms[1].lower.rx_hz == 144_100_000
    assert img.memory.pms[1].upper.rx_hz == 145_900_000


def test_vfo_and_home():
    img = load(CloneImage, ALL_B)
    assert img.setup.vfo_a[Band.VHF].rx_hz == 145_300_000
    assert img.setup.vfo_b[Band.VHF].rx_hz == 145_200_000
    assert img.memory.home_a[Band.VHF].rx_hz == 145_300_000
    assert img.memory.home_b[Band.VHF].rx_hz == 145_400_000


def test_settings_apo():
    img = load(CloneImage, ALL_A)
    assert hasattr(img.setup.settings, "apo")


def test_scan_resume_a_b():
    img = load(CloneImage, ALL_B)
    assert img.setup.settings.scan_resume_a == "5SEC"
    assert img.setup.settings.scan_resume_b == "3SEC"


def test_pms_is_iterable():
    img = load(CloneImage, ALL_B)
    assert len(list(img.memory.pms)) == 50


def test_items_numbered(blank):
    img, _ = blank
    pairs = list(img.memory.channels.items())
    assert pairs[0][0] == 1 and pairs[-1][0] == layout.NUM_REGULAR and pairs[-1][1].number == 999
    assert img.memory.pms[1].lower.number is None
    assert [n for n, _ in img.memory.pms.items()][-1] == layout.NUM_PMS_PAIRS


def test_scan_resume_code_2_is_1sec():
    # Operating manual, 44 SCAN RESUME: BUSY / HOLD / 1 sec / 3 sec / 5 sec
    img = CloneImage(bytes(0x18000))
    img._buf[0xC9] = 2
    assert img.setup.settings.scan_resume_a == "1SEC"


def test_apo_codes_follow_the_manual_options():
    # Operating Manual, 28 APO: 0.5-2.0 h in 0.5 h steps, then 1 h steps to 12 h;
    # the byte counts half-hours (2 = 1.0h, 4 = 2.0h in captures)
    img = CloneImage(bytes(0x18000))
    for code, label in ((4, "2.0h"), (6, "3.0h"), (24, "12.0h")):
        img._buf[layout.APO_OFFSET] = code
        assert img.setup.settings.apo == label
    img._buf[layout.APO_OFFSET] = 5         # not a menu option: raw
    assert img.setup.settings.apo == 5
