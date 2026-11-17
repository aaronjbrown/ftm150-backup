MAGIC = b"AH086$"

CH_STRIDE = 0x10          # 16-byte record, shared by every memory type
CH_BASE = 0x800           # regular CH1 (slots 0..998 = CH1..999)
NUM_REGULAR = 999
NAME_BASE = 0x10000       # regular-channel name tags (16-byte stride)
NAME_MAX = 8              # longest name the radio's entry accepts (spec §5); the tag holds 16
NAME_FLAG_BASE = 0x4CB0   # name-present word per regular channel: 00 00 = named,
NAME_FLAG_STRIDE = 2      #   FF FF = unnamed (spec 8d; ADMS-17 needs it to show names)

PMS_BASE = 0x4670         # PMS-nL = PMS_BASE + (n-1)*0x20 ; U = +0x10
NUM_PMS_PAIRS = 50
PMS_PAIR_STRIDE = 2 * CH_STRIDE   # lower + upper record

BAND_STRIDE = 0x10        # within a VFO/Home block: slot = base + band*0x10
VFO_A_BASE = 0x100
VFO_B_BASE = 0x150
HOME_A_BASE = 0x1a0
HOME_B_BASE = 0x1f0

APO_OFFSET = 0x00A4
SCAN_RESUME_A_OFFSET = 0x00C9
SCAN_RESUME_B_OFFSET = 0x00D9
