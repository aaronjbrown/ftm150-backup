# Yaesu FTM-150 SD-Card Clone (`CLNFTM150nn.dat`) — Format Specification

Reverse-engineered from real backups and controlled ADMS-17 experiments. Software design
is documented separately in [`DESIGN.md`](DESIGN.md).

> **Confidence tags used throughout:** `CONFIRMED` (proven from data or docs) ·
> `LIKELY` (strong evidence, not yet proven) · `HYPOTHESIS` (plausible, needs a test) ·
> `UNKNOWN` (identified but not decoded) · `PARTIAL` (some items decoded, others located only).
>
> **Firmware evidence.** A separate static analysis of the radio's MAIN (V01.03, Renesas RX,
> big-endian) and SUB (V01.02) firmware traced the backup, restore and record codecs. A
> fact taken only from that analysis is tagged `LIKELY (firmware)`; it becomes `CONFIRMED`
> when a capture or a hardware test proves it. The evidence (addresses and tags) is in
> [`firmware-evidence.md`](firmware-evidence.md), one section per spec section.

---

## 1. Overview `CONFIRMED`

Evidence: [firmware-evidence.md §1](firmware-evidence.md).

- The Yaesu **FTM-150R/E** writes a full configuration image to microSD via the radio menu
  **`47 BACKUP` → `WRITE TO SD`**. The same image is read by the **ADMS-17** programming
  software (*Communications → Get Data from SD card*).
- On the card the data lives at: `/FTM150/BACKUP/`
  - `CLNFTM150nn.dat` — the clone image(s). `nn` is a 2-digit slot number (`00`–`09` observed).
  - `$index.dat` — a small index/table-of-contents file (see §3).
- "CLN" = Yaesu's term for **clone** data (a raw image of the radio's configuration memory).
- The image is a fixed-layout binary blob (not a filesystem, not compressed).
- Besides the menu, a PC may be able to put a file on the card over USB: vendor request `0xD1`
  loads up to `0x19000` bytes into the SUB's external-RAM buffer (`0x070E1000`, length at
  `[0x5A1D8]`), and that is the buffer SD op `0x12` writes to a file — enough for a `0x18000`
  image. The shared buffer is `LIKELY (firmware)`; the end-to-end PC→card flow is `LIKELY
  (firmware, inferred)` (its callbacks were not traced) and untested. Evidence:
  `<RE-repo>/docs/notes/sub_rS2.md`.

## 2. The clone image — top level `CONFIRMED`

Evidence: [firmware-evidence.md §2](firmware-evidence.md).

| Property                   | Value                                                                                                                                                 |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| File size                  | **98304 bytes = `0x18000` = 96 KiB**, identical for every file                                                                                        |
| Magic / signature          | ASCII **`AH086$`** (`41 48 30 38 36 24`) at offset `0x00000`                                                                                          |
| Origin                     | A raw dump of the radio's settings EEPROM, seen by the firmware as two 64 KiB I2C address spaces (device-select `0xA0` = EEPROM0, `0xA2` = EEPROM1): file `0x00080`–`0x0FFFF` = EEPROM0 at the same addresses, file `0x10000`–`0x17FFF` = EEPROM1 `0x0000`–`0x7FFF`. The header replaces EEPROM0 `0x0000`–`0x007F`. No records, block checksums or trailer — `LIKELY (firmware)`. The part is probably a single 1 Mbit EEPROM with 256-byte pages (AT24CM01 / M24M01 style), not two 24xx512: one 180-byte page write at `0x6800` would wrap on a 128-byte-page part — `LIKELY (firmware, inferred)` |
| Byte order                 | **Big-endian** (the MAIN CPU is big-endian) — `LIKELY (firmware)`; no multi-byte value in the captures contradicts it                                     |
| Padding / unused           | `0x00` and `0xFF` fill in various reserved zones                                                                                                      |
| Header checksum            | `0x7F` = the low byte of the sum of bytes `0x00`–`0x7E` (`0x4E` in the radio backups tested) — `CONFIRMED`, every image tested, ALL, MEMORY and SETUP. It covers only the header; nothing else in the file is checksummed |
| Header bytes `0x08`–`0x0A` | `01 01 01` in every radio backup — `CONFIRMED`; meaning **market, variant, version** — `LIKELY (firmware)` (§2d)                                     |

`AH086` is Yaesu's internal model/data-revision code for the FTM-150 clone format
(compare the FTM-150 operating-manual document code `EH086`). `$` (`0x24`) is a field
delimiter following the signature.

## 2b. Partial backups: MEMORY and SETUP `CONFIRMED`

Evidence: [firmware-evidence.md §2b](firmware-evidence.md).

Besides "ALL" (`BACKUP/CLNFTM150nn.dat`, the full image), the radio saves **MEMORY**
(`FTM150_MEMORY-CH/MEMFTM150nn.dat`, 41 472 B = `0xA200`) and **SETUP** (`BACKUP/SYSFTM150nn.dat`, 1 024 B). SETUP is the name in the radio's `47 BACKUP` menu and in ADMS-17, even though its file name starts `SYS`; `SYS` below refers to that file. Both are plain concatenations of CLN-image pieces, in **128-byte (`0x80`) blocks**; the header block (`0x00`–`0x7F`, magic `AH086$`) is identical in all three, so the header does not tell the kinds apart — but the sizes differ (ALL `0x18000`, MEMORY `0xA200`, SETUP `0x400`), and the tools detect the kind by size.
Verified **byte-exact** against an ALL backup taken immediately before with no changes in between (`CLNFTM15009` / `MEMFTM15000` / `SYSFTM15000`):

| File offset  | CLN range           | In                             | Content                                                                          |
| ------------ | ------------------- | ------------------------------ | -------------------------------------------------------------------------------- |
| MEM `0x0000` | `0x00000`–`0x0007F` | MEM+SYS                        | header                                                                           |
| MEM `0x0080` | `0x00180`–`0x0027F` | MEM (`0x180`–`0x1FF` also SYS) | VFO B slots 3–4, **Home A/B**, `0x240` FF                                        |
| MEM `0x0180` | `0x00480`–`0x004FF` | MEM                            | 2nd copy of 8-char labels (Home / group names)                                   |
| MEM `0x0200` | `0x00800`–`0x061FF` | MEM                            | channels, PMS, name flags, then constant to `0x61FF`                             |
| MEM `0x5C00` | `0x10000`–`0x145FF` | MEM                            | name tags + FF tail                                                              |
| SYS `0x000`  | `0x00000`–`0x001FF` | SYS                            | header, operating state, SET menu, VFO A/B, Home A, Home B slot 0 (shared block) |
| SYS `0x200`  | `0x00280`–`0x002FF` | SYS                            | settings incl. the `0x02EA` factory table                                        |
| SYS `0x280`  | `0x00500`–`0x0057F` | SYS                            | incl. the `0x0518` text block → **SETUP** setting                                |
| SYS `0x300`  | `0x06800`–`0x068FF` | SYS                            | WX channel names and their name words — `LIKELY (firmware)`; all `FF` in every capture (unset) |

In **neither** but varying across ALL backups (ALL-only data): `0x03B0`–`0x03E7`
(Home B names — `LIKELY (firmware)`, §8c; this is why it differs from `0x0480`), `0x0580`–`0x07FF` (the `0xCA`/`FF`
blocks — so **not** channel flags, see §8c), `0x6F80`–`0x6FCF`,
`0x7E00`–`0x7F3C`. `0x7C00`–`0x7DFF` holds default-valued VFO/settings records that never vary
— `LIKELY` factory-reset defaults.

### Restore behaviour (shared block `0x180`–`0x1FF`) `CONFIRMED` per record, `LIKELY` per region

The shared block is carried by both partial files, but a restore applies **only the records that file owns** (experiment exp_RESTORE). Method:
1. Take fresh back-to-back ALL/MEMORY/SETUP backups (A0/M0/S0; M0 and S0 again matched their A0 blocks byte-exact).
2. Build M1/S1 from M0/S0 with a throwaway script, changing only the frequency bytes (`rec[2..4]`) of three records to distinct markers (M1: 432.100 / 146.100 / 120.100; S1: 432.200 / 146.200 / 120.200).
3. Restore M1 → ALL backup A1. Restore S1 → ALL backup A2.

| Record (CLN offset) | MEMORY restore (A1) | SETUP restore (A2) | Owner |
|---|---|---|---|
| VFO B slot 3 (`0x180`) | not applied | **applied** | SETUP |
| Home A slot 1 (`0x1B0`) | **applied** | not applied | MEMORY |
| Home B slot 0 (`0x1F0`) | **applied** | not applied | MEMORY |

No other byte of A1 or A2 differed from A0. Only one record per role was marked, so ownership is `CONFIRMED` per record and `LIKELY` for the rest of each region (VFO B slot 4 → SETUP; all of Home A and Home B → MEMORY). The radio accepted both modified files. There is no checksum over the partial files beyond the header byte `0x7F` (§2).

Exposure used by the `ftm150` engine (a partial file exposes a record only if it contains
it and a restore applies it):
```
MemoryImage exposes: channels, pms, home_a, home_b
SetupImage exposes: settings, vfo_a, vfo_b
```
`ftm150 extract` writes either partial from an ALL image; `ftm150 merge` overlays partials onto an ALL image owner-masked: in the shared block SETUP supplies only VFO B slots 3–4 and MEMORY only Home A and Home B slot 0; the header is compared (must match), never copied.

## 2c. ADMS-17 `.FTM150` file `CONFIRMED` (layout) / comment arrays `LIKELY`

Evidence: [firmware-evidence.md §2c](firmware-evidence.md).

ADMS-17's File → Save writes a `.FTM150` file on the PC. The radio does not read it; it holds an ALL image plus the ADMS-17 Comment fields, which are not transferred to the radio (ADMS-17 manual). The `ftm150` tools do not read it.

The file is a .NET `BinaryFormatter` stream ([MS-NRBF]) of one object, `ADMS17.FObject`, from assembly `ADMS17, Version=1.0.1.0, Culture=neutral, PublicKeyToken=null`. Five saved files parse end to end with nothing left over. Integers are little-endian.

| Offset    | Record                        | Content                                                 |
| --------- | ----------------------------- | ------------------------------------------------------- |
| `0x00`    | `00` SerializedStreamHeader   | root id 1, header id −1, version 1.0                    |
| `0x11`    | `0C` BinaryLibrary            | library id 2, the assembly name above                   |
| `0x54`    | `05` ClassWithMembersAndTypes | object id 1, class `ADMS17.FObject`, 7 members (below)  |
| `0xCA`    | 7 × `09` MemberReference      | member values: object ids 3–9                           |
| `0xED`    | `0F` ArraySinglePrimitive     | object id 3, length `0x18000`, element type `02` (Byte) |
| `0xF7`    | array data                    | **the ALL image**, `0x18000` bytes, ending at `0x180F7` |
| `0x180F7` | 6 × `11` ArraySingleString    | object ids 4–9, the comment arrays                      |
| last byte | `0B` MessageEnd               |                                                         |

| Member | Id | Type | Length | Holds |
|---|---|---|---|---|
| `buffer` | 3 | `byte[]` | 98 304 | ALL image |
| `NormalMemCmnt` | 4 | `string[]` | 999 | comment per regular channel |
| `PmsMemCmnt` | 5 | `string[]` | 100 | comment per PMS record |
| `HomeAMemCmnt` | 6 | `string[]` | 4 | comment per Home A band |
| `HomeBMemCmnt` | 7 | `string[]` | 4 | comment per Home B band |
| `VfoAMemCmnt` | 8 | `string[]` | 4 | comment per VFO A band |
| `VfoBMemCmnt` | 9 | `string[]` | 4 | comment per VFO B band |

**`buffer` is a plain ALL image.** Three saved files hold an image byte-identical to
`CLNFTM15001`, `CLNFTM15003` and `CLNFTM15006`, with no wrapper or checksum around it.
Everything before it has a fixed size, so the image is always at `0xF7`; the file size varies only with the comment arrays (70–874 bytes observed after the image). `CONFIRMED`

**Comment arrays.** Each element is a null (`0A`, or a run: `0D` with a 1-byte count, `0E` with a 4-byte count), a `06` BinaryObjectString, or a `09` reference to an earlier string.
- Index = record `LIKELY`: a file with 14 channels, PMS-1, Home A/B and VFO A edited on the 144 MHz band had non-null entries at exactly those channels, PMS indexes 0–1, and index 1 of the Home A, Home B and VFO A arrays. So the 4-element arrays run AIR, 144, VHF/UHF, 430.
- Every string observed is empty, so comment text itself has not been seen. MS-NRBF strings are UTF-8 with a 7-bit-encoded length prefix. ADMS-17 allows up to 255 letters per comment.
- What separates a null from an empty string is `UNKNOWN`: the non-null count does not track enabled channels across files (6/6, 0/7, 3/101 and 160/87).

**ADMS-17 behaviour** (ADMS-17 manual). File → Open, Save and Save as stay greyed out until data has been read from the radio or SD card in that session, so read an ALL backup first and then open the file. A file saved for an incompatible transceiver gives an error.

**Blank-template header (ADMS-17).** ADMS-17's blank template has `01 04 5F` at `0x08`–`0x0A`. The radio showed ERROR for two ALL images built on that template, but loaded the same channels from a radio-made base. The template's variant byte (`04`, B3) differs from the radio's (`01`, A2), and a restore refuses a variant mismatch (§2d), so the header is the `LIKELY (firmware)` cause. The `0x0400`–`0x047F` block, which also differs in the template, is never written by a restore, so it cannot be the cause. Tools must never write a template header or block to a radio image.

## 2d. Header `0x00`–`0x7F` `CONFIRMED` (values) / `LIKELY (firmware)` (meaning)

Evidence: [firmware-evidence.md §2d](firmware-evidence.md).

MAIN builds the header in a zeroed buffer:

| Offset | Size | Radio value | Meaning |
|---|---|---|---|
| `0x00` | 7 | `41 48 30 38 36 24 00` | `AH086$\0` model magic |
| `0x07` | 1 | `00` | — |
| `0x08` | 1 | `01` | **Market code**, a copy of EEPROM `0x047F`: 0 USA, 1 EXP, 2 JPN, 3 AUS, 4 CHN |
| `0x09` | 1 | `01` | **Variant (destination) code 0–15**, a copy of EEPROM `0x047D` bits 0–3: 0 ALL, 1 A2, 2 A3, 3 B2, 4 B3, 5 C2, 6 C3, 7 A4, 8 A4B3, 9 TH, 10 THB3, 11 TW, 12 TWB3, 13 F2, 14 F3, 15 FW |
| `0x0A` | 1 | `01` | First byte of the ROM version `01 00 00 03` (V1.03). A restore adds it to the sum but never compares it |
| `0x0B` | 116 | `00` | unused; a restore ignores these bytes |
| `0x7F` | 1 | sum8 | written as the low byte of the sum of `0x00`–`0x7E`. A restore re-sums only bytes `0x00`–`0x06`, `0x08`, `0x09` and `0x0A`, i.e. `0x4B + [0x08] + [0x09] + [0x0A]` |

`0x047D`–`0x047F` hold `01 00 01` in every capture, matching the header. A radio reporting
Main Ver. 1.03 writes `01` at `0x0A`. `0x02FE` holds the same value (`01`, template `5F`) by
coincidence: it is a ROM default byte of the settings block that nothing in the firmware reads
or writes — `LIKELY (firmware)`.

**Restore check** `LIKELY (firmware)`. The radio refuses an ALL file unless the magic matches,
`0x08` equals its own market, `0x09` equals its own variant and the sum8 is right. `0x0A` may
hold any value the sum accounts for, so the ADMS-17 template (`01 04 5F`) fails on its variant
alone. A file from a
radio with another market or variant therefore cannot be restored, and a header edit needs the
sum8 recomputed. A restore writes everything back at the same addresses, **except
`0x0400`–`0x047F`** (identity and alignment, §4), and writes the header itself to EEPROM
`0x0000`. The variant is set only by front-panel dealer codes or the PC link, never from a file.
The PC link also has a raw EEPROM read/write command (64 bytes at an address taken from the
frame; read MAIN `fffad5c0`, write PC cmd `0xF4` at MAIN `fffad635`). The write **refuses any
start address `0x400`–`0x47F`**: it NAKs (`0x15`) when `0x400 ≤ addr < 0x480` (MAIN
`fffad651`–`fffad65d`) — `LIKELY (firmware)`. The guard checks only the start address, but a
64-byte poke starting at `0x3C1`–`0x3FF` is one I2C page-write and `0x400` is a page boundary,
so the EEPROM wraps within its page and the poke cannot reach the block either — `LIKELY
(firmware, inferred)`. A second, 2-byte raw write (PC cmd `0xF1`, MAIN `fffad4e8`) has **no
address check**, so the PC link can still write the identity bytes — `LIKELY (firmware)`, read
from the disassembly. So no file and no 64-byte poke writes the identity bytes; the 2-byte
poke, the service adjust mode, a full reset, the dealer codes and the PC link's variant command
can (evidence: `<RE-repo>/docs/notes/main_backup_content.md`, `link_protocol.md`).

**What each restore writes** `LIKELY (firmware)`; the shared-block records marked in the
experiment above are `CONFIRMED`:

| Restore | Writes (CLN offsets) | In the file but not written |
|---|---|---|
| ALL | `0x00000`–`0x003FF` (header to EEPROM `0x0000`), `0x00480`–`0x17FFF` | `0x0400`–`0x047F` |
| MEMORY | `0x01A0`–`0x023F` (all Home A and Home B records), `0x0480`–`0x04CF` (Home A names), `0x0800`–`0x61FF`, `0x10000`–`0x145FF` | `0x0180`–`0x019F` (VFO B slots 3–4), `0x0240`–`0x027F`, `0x04D0`–`0x04FF` (Home name words) |
| SETUP | `0x0080`–`0x019F` (current A/B, state, VFO A, VFO B), `0x0280`–`0x02FF`, `0x0500`–`0x057F`, `0x6800`–`0x68B3` (WX names and words) | `0x01A0`–`0x01FF` (Home A, Home B slot 0: the shared block, owned by MEMORY), `0x68B4`–`0x68FF` |

Checked against the firmware's restore ranges (2026-11-15), together with the file layouts in
§2b: they agree. The SETUP row's unwritten bytes follow from the SETUP layout and its write list.

So a MEMORY restore writes Home A names without their name words, and never writes the Home B
names at `0x03B0` (not in the file). `ftm150 merge` differs from this table in three places:
for MEMORY it also copies `0x0240`–`0x027F` and the Home name words `0x04D0`–`0x04FF`, and for
SETUP it does not copy `0x6800`–`0x68B3`. The bytes involved are constant or `FF` in the
captures except the Home name words; aligning merge waits on a hardware test.

**After a restore** `LIKELY (firmware)`. The boot path (MAIN `ee_load_all_at_boot`) runs two
fix-ups on every boot, and the radio reboots after a restore, so a restored image can differ
slightly from the file:
- a VFO record for band slot 2 (174–400 MHz) holding 174.000 MHz (`01 74 00` in `rec[2..4]`;
  bytes `0x22`–`0x24` of the VFO block) is read back as `rec[2]` = `0x81`, 174.005 MHz (MAIN
  `fff97307`) — a migration fix-up; its meaning is inferred;
- each byte of the 5-character ID at `0x0478`–`0x047C` outside `0-9`/`A-Z`/`a-z` becomes `*`.
  The ID is in the block no restore writes (§4), so a file's ID bytes have no effect; the
  fix-up acts on the radio's own ID.

Evidence: `<RE-repo>/docs/notes/main_rB.md`.

**Card and power loss** `LIKELY (firmware)`:
- The radio's file system handles FAT12/16/32 only; no allocation path handles exFAT, so a card
  must be FAT-formatted (the radio's own SD FORMAT does that).
- Its journal (`LMREPAIR` on the card) protects directory metadata only. A power cut during a
  backup leaves, after replay, a file shorter than its kind's size; the index rebuild sorts by
  exact size (§3), so the short file is ignored rather than offered for restore (the outcome is
  inferred).

Evidence: `<RE-repo>/docs/notes/sub_rS1.md`, `sub_sd_writer.md`.

## 2e. Not in any backup `LIKELY (firmware)`

Evidence: [firmware-evidence.md §2e](firmware-evidence.md).

Two kinds of radio data are in none of the three backup files, so a restore cannot bring
them back:
- **Bluetooth paired-device list.** It sits in MAIN RAM `0x303C8` (8 × 28 B: name and hex
  address) and is cleared at boot (MAIN `fff98fe2`); it has no EEPROM address. Only the
  Bluetooth on/off bit (`0x00F9` bit 1, §8c) is in the image.
- **Voice recordings.** The FVS-2 voice unit keeps its recordings itself, and the SUB voice
  recorder writes standard WAV files (16 kHz, 16-bit mono) on the card as files of their own. The image holds
  only the voice settings and the FVS-2 track count and flags (`0x00DC`/`0x00DD`, §8c).

Evidence: `<RE-repo>/docs/notes/main_rE.md`, `main_rF.md`, `sub_rS2.md`.

## 3. `$index.dat` `LIKELY`

Evidence: [firmware-evidence.md §3](firmware-evidence.md).

- 720 bytes = **3 tables × 10 slots × 24 B**, one table per backup kind:
  ALL (`CLN…`) @ `0x000`, MEMORY (`MEM…`) @ `0x0F0`, SETUP (`SYS…`) @ `0x1E0`.
- Entry (24 B): **6-byte BCD timestamp `YY MM DD hh mm ss`**, then the **file name without
  `.dat`**, ASCII, NUL-padded to 18 B. An empty slot is all `0x00`.
- Entries are listed **newest first**.
- Each timestamp equals the file's FAT modification time as read on the host in UTC. This
  matched for all 7 entries observed.
- The radio's SUB CPU rebuilds the index by scanning the folders (SUB `ffe6667b`). It sorts
  files into the three tables **by size alone** (`0x18000` / `0xA200` / `0x400`) and skips
  files dated before 2000 — `LIKELY (firmware)`.
- **When it is rebuilt** `LIKELY (firmware)`. Only three call sites reach the rebuild:
  - link op `0x73` (SUB `ffe68b16`), which MAIN sends **only from SD FORMAT** (SET item 48
    handler MAIN `fffb40ca`; the sole write of link request `0x08` is at MAIN `fffb4153`);
  - the card-mount edge (SUB `ffe6b43c`): power-up or card insertion;
  - a third path (SUB `ffe6b534`) that is dead code, since nothing sets its trigger.

  The backup write path (ops `0x05`/`0x06`/`0x11`) never reaches it, and no backup path sends
  op `0x73`. **So after a backup the card's `$index.dat` is stale until the next power-up, card
  re-insertion or SD FORMAT.** MAIN shows the new backup from its RAM copy in the meantime. A
  host reading the card straight after a backup therefore sees an index without the newest
  file; tools should list backups from the directory, not from `$index.dat`.
- **Clock** `LIKELY (firmware)` (mechanism). SUB has no battery-backed clock: a software clock
  starts at **2024-06-01 00:00** on every boot. The only other setter is the index rebuild,
  which keeps a running maximum of the entries' timestamps while it scans (SUB
  `ffe6796e`–`ffe679ae`) and then sets the clock to it (SUB `ffe68222`). After each mount the
  clock therefore jumps to the newest file on the card, and the next backup is stamped at or
  after it. Two consequences: newest-first order holds, and a radio-made backup is never dated
  before 2000, so the year-2000 filter does not hide it (inferred). Evidence:
  `<RE-repo>/docs/notes/sub_sd_writer.md`.
- The radio rebuilds the index from the directory. Files copied onto the card from a PC
  (not written by the radio) were listed with their copy time, and restored normally.
  Tools therefore never need to write `$index.dat`.
- Observed after the radio backups of exp_RESTORE. The captured `$index.dat` holds the
  all-zero state. `LIKELY` because it rests on one populated observation. 10 slots per
  kind fits the table size (`0xF0` / 24) and the ADMS-17 manual's limit of 10 files per kind;
  only slots `00`–`02` have been seen.

## 4. High-level memory map `CONFIRMED` (boundaries) / content confidence noted

Evidence: [firmware-evidence.md §4](firmware-evidence.md).

Derived by diffing 7 real images (files vary → live config; identical → fixed/reserved).

| Offset range | Size | Varies across files? | Content (confidence) |
|---|---|---|---|
| `0x00000`–`0x0007F` | 128 B | no | **Header** (§2d) — `CONFIRMED` |
| `0x00080`–`0x0009F` | 32 B | yes | Current A/B channel records (§8c) — `LIKELY` |
| `0x000A0`–`0x000FF` | 96 B | yes | Operating state and global **set-menu** settings (e.g. **APO @ `0x00A4`**) (§8c) — `PARTIAL` |
| `0x00100`–`0x0023F` | ~320 B | yes | Per-band **VFO A/B + Home A/B** (§8) — `CONFIRMED` |
| `0x00240`–`0x007FF` | ~1.4 KiB | yes | More settings, DTMF memories `0x0300`, Home names `0x03B0`/`0x0480`, unknown text block `0x0518` (§6, §8c); contains the `0x0400` block below — `PARTIAL` |
| `0x00400`–`0x0047F` | 128 B | no (fixed across this radio's backups, different in the ADMS-17 template) | Per-unit identity and alignment: RF parameters `0x0400`–`0x045F`, a 5-character ID `0x0478`–`0x047C` (`FF` here), variant `0x047D`, layout stamp `0x047E`, market `0x047F`. **Never written by a restore** — `LIKELY (firmware)` |
| `0x00800`–`0x0466F` | ~15 KiB | yes | **999 regular memory-channel records**, 16 B each (§7) — `CONFIRMED` |
| `0x04670`–`0x04CAF` | ~1.5 KiB | yes | **PMS pairs** (50×2 records), same 16 B format (§8b) — `CONFIRMED` |
| `0x04CB0`–`0x0547D` | ~2 KiB | yes | **Name-present words**, 2 B per regular channel (§8d) — `CONFIRMED` |
| `0x0547E`–`0x05545` | 200 B | no | Name-present words for the 100 PMS records (§8d) — `LIKELY (firmware)`; `FF` in every capture |
| `0x05546`–`0x055FF` | — | no | Reserved / padding — `LIKELY` |
| `0x05600`–`0x0564F` | 80 B | no | **PMG list**, 5 × 16 B (§8c) — `LIKELY (firmware)` |
| `0x05650`–`0x05FFF` | — | no | Reserved / padding — `LIKELY` |
| `0x06000`–`0x07FFF` | 8 KiB | partial | Secondary config incl. WX names `0x6800` (§8c) and the 2nd unknown text block (§6) — `UNKNOWN` |
| `0x08000`–`0x0FFFF` | 32 KiB | **no (identical all files)** | Upper EEPROM0; the firmware has no accessor here outside the bulk dump — `UNKNOWN` |
| `0x10000`–`0x13E6F` | ~15 KiB | yes | **999 memory-channel NAME TAGS**, 16 B each (§5) — `CONFIRMED` (EEPROM1 starts here) |
| `0x13E70`–`0x144AF` | 1600 B | no | Name tags for the 100 PMS records (§8b) — `LIKELY (firmware)`; `FF` in every capture |
| `0x144B0`–`0x17FFF` | ~15 KiB | no | Reserved / padding — `LIKELY` |

> Memory-channel records (freq/tone/mode/flags) are fully decoded — see §7. The channel
> array starts at `0x0800`.

## 5. Memory-channel name tags @ `0x10000` `CONFIRMED`

Evidence: [firmware-evidence.md §5](firmware-evidence.md).

- Array of **16-byte records**, one per memory slot, `0x10000`–`0x13E6F` (**999 entries**).
- Encoding: ASCII characters, then **`0xFF` padding** to fill the record.
  - Example: `52 50 54 32 4D 2D 41 FF FF …` = `"RPT2M-A"`.
- An all-`0xFF` record = **no tag** for that slot. The radio ends a name at any byte ≥ `0xF0` —
  `LIKELY (firmware)`.
- The array continues for the 100 PMS records (record index 999–1098, `0x13E70`–`0x144AF`),
  so it has 1 099 entries in all — `LIKELY (firmware)`; §8b.
- Slot index = `(offset − 0x10000) / 0x10`; **channel number = index + 1** `CONFIRMED`
  (exp_Q: tag `LAST` on CH999 → data `0x4660`, name `0x13E60`).
- A memory tag can be entered with up to 8 characters (Operating Manual, Edit memory tag; ADMS-17 enforces the same limit, operator-reported). `CONFIRMED`
  The ADMS-17 manual's Name items say "up to 16 digits", while the operator reports ADMS-17 accepting 8 and the Operating Manual says 8; the entry limit rests on the Operating Manual.
- Each record holds 16 bytes, so the image can store a longer name than the radio's entry limit. `CONFIRMED`
- **Open:** whether trailing bytes of each 16-B record carry non-name metadata. `UNKNOWN`
- **Open:** radio behaviour on loading a 9–16 character tag. `UNKNOWN`

### Ground-truth anchor (very useful for future decoding)
UHF CB frequencies are standardised, so an Australian 80-channel UHF CB bank (`CB CH1`…`CB CH80`,
`EMERGNCY` on ch5 and ch35) gives known-value anchors.

## 6. Unknown text blocks at `0x0518` / `0x7D98` — NOT APRS `UNKNOWN`

Evidence: [firmware-evidence.md §6](firmware-evidence.md).

The FTM-150 has **no APRS** (operator-confirmed), so these blocks are not APRS data.

A short block with printable bytes appears **twice**: `~0x0518` and `~0x7D98`
(constant `0x7880` apart). Contents include `2A×7` = `"*******"` and `2F 3E 2F 52` =
`"/>/R"`. True meaning unknown — candidates: C4FM "My Callsign" / opening (startup)
message / GM. Decode via an experiment (set the callsign or opening message in ADMS-17).
The two blocks are **not** a full-image mirror (tested: <45 % similarity; `0x7880` is
`0xFF`-filled) — **no dual-bank config mirror exists** in this format. `CONFIRMED` (no mirror)

The radio's main firmware never addresses `0x0500`–`0x07FF` or `0x7C00`–`0x7F3F`: only the
bulk backup/restore copies them (`0x0500`–`0x057F` in SETUP and ALL) and the PC link's raw
EEPROM read/write can reach them. Their owner is probably the PC software or the factory —
`LIKELY (firmware)`.

## 7. Memory-channel record @ `0x0800` `CONFIRMED` (decoded via ADMS-17 experiments + real-data cross-check)

Evidence: [firmware-evidence.md §7](firmware-evidence.md).

- **Array base = `0x0800` (= Memory Channel 1), stride = `0x10` (16 bytes), 999 channels
  (`0x0800`–`0x0466F`).** Channel *n* record is at `0x0800 + (n-1)*0x10`.
  Parallel name-tag array at `0x10000` (§5). Empty slot template below.
- Decoded by single-variable ADMS-17 experiments (`exp_A..E`) and confirmed
  against real programmed channels in the reference files (repeaters and standardised
  Australian UHF-CB frequencies).

Record byte layout (offsets relative to record start; `rec[i]`):

| Byte | Field | Encoding | Confidence |
|---|---|---|---|
| `rec[0]` | **flags + band** | bit `0x80` = channel used/enabled; bit `0x20` = **SCAN skip** (SCAN=NO); bit `0x08` = **M-GRP** (memory group); low 3 bits = **band code** (see table below). Bits `0x40`/`0x10`/`0x04` reserved. | `CONFIRMED` |
| `rec[1]` | **mode + shift + flags** (packed) | bit `0x20` = **Narrow**; bit `0x10` = **AM** (clear = FM); low 3 bits = **shift mode**: `0`=simplex, `2`=−RPT, `3`=+RPT, `4`=odd/split. bit `0x40` = **internal flag, NOT a user setting** (see note). bit `0x08` = reverse — `HYPOTHESIS (firmware)`. | shift/AM/narrow `CONFIRMED`; `0x40` = internal |
| `rec[2]` | **fraction code + freq top digit** | low nibble = top BCD digit of RX freq; **high nibble = sub-10 kHz fraction code** (table below) | `PARTIAL` (codes `0`/`4`/`8`/`C` `CONFIRMED`) |
| `rec[3]` | **RX freq mid BCD** | two BCD digits | `CONFIRMED` |
| `rec[4]` | **RX freq low BCD** | two BCD digits | `CONFIRMED` |
| `rec[5]` | **tone mode + step** | high nibble = **tone mode**: `0`=off, `1`=TONE (enc), `2`=TSQL (enc+dec), `4`=DCS. The firmware's menu list continues 3 REV TONE, 5 PR FREQ, 6 PAGER, 7 DCS ENC (DC), 8 TONE DCS (T-D), 9 DCS TSQL (D-T), 10 "JR FREQ" — `LIKELY (firmware)`, untested. 7–9 need the squelch-expansion setting; 10 exists only in regions whose low nibble is ≥ `0xD` (not this EXP/A2 radio), and 11 is never selected. Low nibble = **tuning step** (step codes below). | tone 0/1/2/4 `CONFIRMED`; step per code |
| `rec[6]` | **TX fraction code + top digit** | odd-split **TX frequency**, same encoding as `rec[2]`. Meaningful when `rec[1]` shift = split(`4`); else `00`. | `CONFIRMED` |
| `rec[7..8]` | **TX freq mid/low BCD** | odd-split TX freq (as `rec[3..4]`) | `CONFIRMED` |
| `rec[9]` | **Tx power + CTCSS index** | bits 7–6 = **Tx Power** (`00`=HIGH, `01`=MED, `10`=LOW); bits 5–0 = 0-based index into standard 50-tone CTCSS table (`0x09`=91.5, `0x0c`=100.0 Hz). | `CONFIRMED` |
| `rec[10]` | **Clock Shift + DCS index** | bit `0x80` = **Clock Shift**; bits 6–0 = 0-based index into standard DCS code list (`0`=023, `0x21`=205). | `CONFIRMED` |
| `rec[11]` | **Display + User CTCSS** | bit `0x80` = **memory display**: 1 = name is the main field, 0 = frequency (setting 15 channels to name display on the radio flipped only this bit, CLNFTM15006→07). Bits 4–0 = **User CTCSS** ÷ 100 Hz: `0x0f`=1500 Hz (default), `0x0a`=1000, `0x03`=300 (min/empty); range `0x03`–`0x1e` (300–3000 Hz). Bits 6–5 are undecoded: the firmware masks the value with `0x1F`, and they are 0 in every capture. | `CONFIRMED` (mask `LIKELY (firmware)`) |
| `rec[12]` | **repeater offset, high byte** | `rec[12..13]` = one big-endian u16 of 50 kHz units — `LIKELY (firmware)`. The radio's menu allows 0.00–99.95 MHz (Operating Manual, 23 RPT SHIFT FREQ) — `CONFIRMED`, which does not fit one byte: stored 0–1999 (`07 CF`), so `rec[12]` is 0–7 and is non-zero from 12.80 MHz (`01 00`) up. `00` in every capture, since none has an offset ≥ 12.80 MHz. Until confirmed, the tools refuse to read a non-zero `rec[12]` and clear it on an offset write. | `LIKELY` |
| `rec[13]` | **repeater offset** | `uint8 × 50 kHz` (no flag bit): `0x0c`=600 kHz, `0x64`=5 MHz, `0x8c`=7 MHz (verified on a repeater with a real 7 MHz split). Applied per `rec[1]` shift dir. | `CONFIRMED` |
| `rec[14..15]` | reserved | `00` | — |

> **`rec[1]` bit `0x40` — internal flag (not user-editable).** Investigated exhaustively:
> it is *not* C4FM (the FTM-150R/E has no digital voice — the "SPU-1 digital signal
> processing" is noise reduction only), *not* transmit-enable (a normal TX repeater has it clear), *not* one of ADMS-17's 19 memory columns, and *not* any per-channel
> setting in the operating manual. It is uncorrelated with every decoded field (set on
> 95/312 real channels, no predictor among band/mode/shift/tone/power/skip/CB). Treated as
> an opaque bit: preserved verbatim on same-base edits; not represented in CSV. Meaning
> `UNKNOWN`. It was set on records edited in ADMS-17, cleared on older records after a later
> ADMS-17 round trip, and the radio kept it on restore (`HYPOTHESIS`: a marker for records
> edited in that session).

Worked frequency examples (real files): `01 46 90`→146.900; `84 76 42`→476.425 (code `8`);
`04 76 45`→476.450; `C4 76 43`→476.4375 (code `C`); `44 76 46`→476.4625 (code `4`).

### Fraction codes (`rec[2]` / `rec[6]` high nibble) `PARTIAL`
The firmware decodes the high nibble as a code that adds a sub-10 kHz fraction to the BCD
frequency. Codes `0`/`4`/`8`/`C` are proven by the standard 80-channel Australian UHF CB
plan in the captures: CB CH1–40 are on the 25 kHz grid (codes `0`/`8`), CB CH41–80 sit
12.5 kHz between them (codes `C`/`4`). The bits `0x80`/`0x40`/`0x20` weigh 5 / 2.5 / 1.25
kHz, and `0x10` marks the third-of-a-kHz values.

| Code | Adds | Confidence |
|---|---|---|
| `0` | 0 | `CONFIRMED` |
| `4` | 2.5 kHz | `CONFIRMED` (CB CH42 = 476.4625) |
| `8` | 5 kHz | `CONFIRMED` (ADMS-17 experiments; CB CH1 = 476.425) |
| `C` | 7.5 kHz | `CONFIRMED` (CB CH41 = 476.4375) |
| `2` / `6` / `A` / `E` | 1.25 / 3.75 / 6.25 / 8.75 kHz | `LIKELY (firmware)`: produced only on the 6.25 kHz step |
| `3` / `5` / `B` / `D` | 1.667 / 3.333 / 6.667 / 8.333 kHz | `LIKELY (firmware)`: produced only on the 8.33 kHz (air) step |
| `1` / `7` / `9` / `F` | — | not in the firmware's table |

The firmware's step-snapping code builds the codes from per-step ROM tables: 6.25 kHz gives
`0 2 4 6 8 A C E`, 8.33 kHz gives `0 3 5 8 B D`, 12.5 kHz gives `0 4 8 C`, and 5/10/15/20 kHz give
only `0` or `8`. So codes other than `0`/`4`/`8`/`C` appear only on 6.25 kHz or air 8.33 kHz
channels.

The tools decode the confirmed codes only (a 2.5 kHz frequency grid) and refuse to read a
frequency with any other code, rather than reporting a different frequency.

### Reference decode (CONFIRMED via exp_A..L)
```
enabled = bool(rec[0] & 0x80)
skip    = bool(rec[0] & 0x20)            # SCAN = NO
mgrp    = bool(rec[0] & 0x08)            # memory group
band    = rec[0] & 0x07                  # 1=2m, 3=70cm
narrow  = bool(rec[1] & 0x20)
mode    = "AM" if rec[1] & 0x10 else "FM"
shift   = {0:"simplex",2:"-RPT",3:"+RPT",4:"split"}[rec[1] & 0x07]
FRACTION_kHz = {0x0: 0, 0x4: 2.5, 0x8: 5.0, 0xC: 7.5}   # confirmed codes (see below)
rx_MHz  = int(f"{rec[2]&0xf}{rec[3]>>4}{rec[3]&0xf}{rec[4]>>4}{rec[4]&0xf}")/100.0 + FRACTION_kHz[rec[2]>>4]/1000
tx_MHz  = int(f"{rec[6]&0xf}{rec[7]>>4}{rec[7]&0xf}{rec[8]>>4}{rec[8]&0xf}")/100.0 + FRACTION_kHz[rec[6]>>4]/1000  # split only
step    = STEP_TABLE[rec[5] & 0x0f]      # see step codes: 0=5k, 1=6.25k, 3=10k, 4=12.5k, 5=15k, 6=20k, 7=25k, 8=50k, 9=100k
tone_mode = {0:"OFF",1:"TONE",2:"TSQL",4:"DCS"}[rec[5] >> 4]
power   = {0:"HIGH",1:"MED",2:"LOW"}[rec[9] >> 6]
ctcss   = CTCSS_TABLE[rec[9] & 0x3f]     # standard 50-tone table
clk_shift = bool(rec[10] & 0x80)
dcs     = DCS_TABLE[rec[10] & 0x7f]      # standard DCS list
user_ctcss_Hz = (rec[11] & 0x1f) * 100   # 300..3000
show_name     = bool(rec[11] & 0x80)     # display name vs frequency
offset_kHz = rec[13] * 50                # repeater offset (non-split shift)
# NOTE: the ADMS-17 "Comment" column is NOT stored in the clone image (only in .FTM150, §2c).
```

### Empty-channel template `CONFIRMED`
An unused slot = `01 00 01 44 00 00 00 00 00 00 00 03 00 00 00 00`
(disabled, band 2 m, 144.000). `rec[0]` lacks the `0x80` enable bit and `rec[11]`=`0x03`.

### Channel record coverage
Every ADMS-17 per-channel column is mapped and confirmed (freq, band, mode, shift, offset,
split TX, step, tone mode, CTCSS, DCS, Tx power, Narrow, Clock Shift, SCAN/skip, M-GRP,
User CTCSS). Not decoded:
- `rec[1]` bit `0x40` — set by ADMS-17, not a user field (best guess: internal flag). `LIKELY`
- `rec[0]` bits `0x40`/`0x10`/`0x04`, `rec[14..15]` — reserved (`00` in all samples).
- `rec[12]` — `00` in all samples; the offset's high byte (see the table), not yet seen non-zero.
- Fraction codes other than `0`/`4`/`8`/`C`.
- **Comment** column is *not* stored in the image (verified: text absent); ADMS-17 keeps it in
  the `.FTM150` file (§2c).

### Step codes (`rec[5]` low nibble) `PARTIAL`
The table is proven on memory channels only.
A memory channel has no AUTO step: ADMS-17 offers 5, 6.25, 10, 12.5, 15, 20, 25, 50 and
100 kHz (operator-confirmed). AUTO belongs to the radio's `26 STEP` menu and to the AUTO STEP
checkbox on ADMS-17's VFO page. It is stored as a flag, not a step code: `0xE3`/`0xF3` bit 3
(§8c) — `LIKELY (firmware)`. The firmware's step labels give the same code order as this table.

| Code | Step | Evidence | Confidence |
|---|---|---|---|
| `0` | 5 kHz | an ADMS-17 file with one channel per step | `CONFIRMED` |
| `1` | 6.25 kHz | same | `CONFIRMED` |
| `3` | 10 kHz | same | `CONFIRMED` |
| `4` | 12.5 kHz | same | `CONFIRMED` |
| `5` | 15 kHz | same | `CONFIRMED` |
| `6` | 20 kHz | same | `CONFIRMED` |
| `7` | 25 kHz | same | `CONFIRMED` |
| `8` | 50 kHz | same | `CONFIRMED` |
| `9` | 100 kHz | same | `CONFIRMED` |
| `2` | 8.33 kHz | never observed in a capture; the radio's list has 8.33 kHz for Air only, between 6.25 and 10; the firmware's step labels give the same order and its step-snapping code uses the 8.33 kHz table for code 2 (evidence §7) | `LIKELY (firmware)` |

Firmware evidence (evidence §8): AUTO STEP is stored as a flag, `0xE3`/`0xF3` bit 3 —
`LIKELY (firmware)`; this supersedes `UNKNOWN` above.

### Band codes (`rec[0]` low 3 bits) `CONFIRMED`
The radio has **exactly 4 bands**, defined by RX frequency range (per operator + captures
exp_Z0/exp_Z2):

| Code | Band name | RX range | Evidence |
|---|---|---|---|
| `0` | AIR (AM) | 108–137 MHz | exp_Z0 = 120.000 AM → `rec[0]=0x80` |
| `1` | 144 / VHF | 137–174 MHz | 2 m channels (`rec[0]=0x8?` low3=1) |
| `2` | VHF / UHF | 174–400 MHz | exp_Z2 = 223.500 → `rec[0]=0x82` |
| `3` | 430 / UHF | 400–550 MHz | 70 cm + UHF-CB channels (low3=3) |

> The `rec[0]=4` / 850 MHz record seen in the VFO block (§8) is **not** a channel band —
> ADMS-17 won't create an 850 MHz memory. Its meaning in the VFO region is `UNKNOWN`.
> Air-band **8.33 kHz** channels would use the third-of-a-kHz fraction codes (§7) — `LIKELY
> (firmware)`, untested (25 kHz air channels encode fine).
> The firmware's VFO band table runs AIR 108–137, 137–174, 174–400, 400–470 and code 4 = 470+;
> captures put 476–477 MHz UHF CB in code 3, so its 400–470 edge is wrong for memories.

## 8. Per-band VFO / band-stack records @ `0x0100`–`0x023F` `CONFIRMED`

Evidence: [firmware-evidence.md §8](firmware-evidence.md).

A **separate memory enumeration** from the 999-channel bank: repeating **16-byte records**
(same field layout as §7) in **5-record blocks**, **4 blocks**
(`0x100`,`0x150`,`0x1a0`,`0x1f0`) = VFO A, VFO B, Home A, Home B (table below).
Example block:
```
00 10 01 08 ...  slot 0  108.0   (AIR band, code 0)
01 02 01 46 90…  slot 1  146.90  (144/VHF, code 1)
02 00 02 22 ...  slot 2  222.0   (VHF/UHF, code 2)
03 00 04 30 ...  slot 3  430.0   (430/UHF, code 3)
04 00 08 50 ...  slot 4  850.0   (NOT a user band — see note in §7 band table)
```
The radio has **dual VFO (A/B)** and **dual Home (A/B)**. The 4 blocks are 5 records each
(one per band slot 0–4; slot 4 = 850 MHz has no user-band equivalent). Each block band-slot
= `block_base + band*0x10`. Assignment `CONFIRMED` via exp_ABHM (VHF set to 4 distinct freqs); all A/B band rows
also cross-checked against ADMS-17's VFO pages (CLNFTM15007):

| Block base | Role | Evidence (exp_ABHM VHF `@base+0x10`) |
|---|---|---|
| `0x0100` | **VFO A** | 145.100 |
| `0x0150` | **VFO B** | 145.200 |
| `0x01a0` | **HOME A** | 145.300 |
| `0x01f0` | **HOME B** | 145.400 |

Records use the identical §7 16-byte format, and VFO and Home records carry a step value in
`rec[5]`. Their step codes are unpaired: VFO records hold codes 0, 4, 6 and 7, Home
records 0, 4 and 7, and PMS records 0 and 4, none matched to a display, and a VFO code 0
could mean AUTO.

## 8b. Special memories: PMS pairs `CONFIRMED`

Evidence: [firmware-evidence.md §8b](firmware-evidence.md).

The FTM-150 has **1103 memory channels total = 999 regular + 50 PMS pairs (100) + 4 Home**
(operating manual: "Using the Memory" and the features list). The manual's 4 Home channels
are one per user band (AIR, 144, VHF/UHF, 430; the manual recalls "the home channel
frequency of the currently selected band"); in the image they are stored per receiver in the
Home A and Home B blocks (§8), slots 0–3 for those bands (slot 4, 850 MHz, is not a user band).
- **Regular** CH1–999: slots 0–998, `0x0800`–`0x466F`.
- **PMS** scan-edge pairs: **slots 999–1098, `0x4670`–`0x4CAF`** (100 records = 50 pairs),
  then `0xFF`. Layout: PMS-*n* Lower = `0x4670 + (n-1)*0x20`, Upper = `+0x10`. Confirmed by
  exp_PM (PMS-1 L=144.100 → `0x4670`, U=145.900 → `0x4680`). Same §7 record format.
- **Home**: in the `0x01a0` / `0x01f0` blocks (§8), *not* in this array.

The operating manual allows a memory tag on Home and PMS channels as well as regular ones.
- **PMS tags** continue the §5 name array: PMS record *k* (0–99) at `0x13E70 + 16·k`, its
  name word at `0x547E + 2·k` — `LIKELY (firmware)`. Both are `FF` in every capture (no PMS
  has been named).
- **Home tags**: Home A at `0x0480`, Home B at `0x03B0`, 5 × 16 B each (§8c) — `LIKELY` (firmware + captures).

---

## 8c. Global SET-menu & settings regions `PARTIAL`

Evidence: [firmware-evidence.md §8c](firmware-evidence.md).

Region survey (bytes varying across the 7 real configs):

| Region | Nature | Notes |
|---|---|---|
| `0x0080`–`0x009F` | 2 channel-format records | Current A/B channel, saved at power-down and flushed before a backup — `LIKELY` |
| `0x00A0`–`0x00FF` | **Packed SET-menu** and operating state | 1 byte per menu item, small enum values. **APO = `0x00A4`** (0=OFF,1=0.5h,…, 0.5 h steps) `CONFIRMED`. ~30 bytes vary. Decode item-by-item via experiments. State bytes below. |
| `0x0240`–`0x02FF` | mixed settings | `0x0280`–`0x02FF` is one 128-byte settings block to the firmware; `0x02EC`–`0x02F7` = last selected menu item per category — `LIKELY (firmware)`, below |
| `0x0300`–`0x038F` | DTMF memories 1–9 | 16 B each: digit codes ending in `FF`; `FF` in byte 0 = empty — `LIKELY (firmware)`; all `FF` in every capture |
| `0x03B0`–`0x03FF` | **Home B names** | 5 × 16 B, one per band slot — `LIKELY` (firmware + captures, below) |
| `0x0480`–`0x04CF` | **Home A names** | 5 × 16 B — `LIKELY` (firmware + captures). Name words (§8d): Home A slot *s* at `0x04D0 + 2·s`, Home B at `0x04E0 + 2·s` |
| `0x0580`–`0x05BF`, `0x0600`–`0x07FF` | `0xCA`/`FF` blocks | **Not channel flags**: excluded from MEMORY backups (§2b) and unchanged as ~95 named channels were added. Role `UNKNOWN` |
| `0x5600`–`0x564F` | PMG list | 5 × 16 B. Byte 0 bit 7 = used; with bit 4 set, `+2..+3` = u16 channel index, otherwise the entry is an inline channel record — `LIKELY (firmware)`. Every capture holds one unused entry. |
| `0x6800`–`0x689F`, `0x68A0`–`0x68B3` | WX channel names and name words | 10 × 16 B, 10 × 2 B — `LIKELY (firmware)`; all `FF` |

The two name blocks are not copies of one label: they belong to Home A and Home B, which is
why they differ in the captures. In every capture the names fit their Home records' bands
(Home A: an AIR tower name on slot 0 at 124.700, a 2 m repeater name on slot 1 at 147.000;
Home B adds a 70 cm repeater name on slot 3 at 439.975), and exactly the named slots have a
`00 00` word (`0x04D0`/`0x04D2`, `0x04E0`/`0x04E2`/`0x04E6`). A MEMORY backup carries `0x0480` (Home A) but not `0x03B0`
(Home B), so a MEMORY restore may not carry Home B names (`HYPOTHESIS`, untested).

**Operating-state bytes** `LIKELY (firmware)` unless marked:

| Offset | Content |
|---|---|
| `0x00A0` | Region byte = `0x30` + variant (`0x31` = A2 in every capture); most of the firmware reads the variant from here |
| `0x00C0` / `0x00D0` | Band A / B mode: 0 VFO, 1 memory, 2 memory-tune |
| `0x00C2`–`0x00C3` / `0x00D2`–`0x00D3` | Current memory channel, u16 big-endian, 0-based (low byte `CONFIRMED`, below) |
| `0x00C4` / `0x00D4` | VFO band |
| `0x00C7` / `0x00D7` | DTMF slot |
| `0x00E3` / `0x00F3` | PMG / scan flags |
| `0x00FF` | Init magic: `AA` valid (every capture), `55` soft reset, `FF` uninitialised; an image with `FF` here probably triggers a factory reset |

**More settings and state bytes** `LIKELY (firmware)` unless marked (firmware naming pass,
2026-11-14). Band B is band A + `0x10` where two offsets are given.

| Offset | Content |
|---|---|
| `0x00A9` | Voice-guide VOLUME 0–2 (LOW / MID / HIGH); also sent to the voice unit at init and on change |
| `0x00AE` | Voice ANNOUNCE: 0 OFF, 1 MANUAL, 2 AUTO |
| `0x00B9` / `0x00BA` | Volume, band A / B, 0–31 (the volume knob; saved with the state block at power-down) |
| `0x00BE` | Current SET-menu category, 0–11 |
| `0x00BF` | Selected soft-key slot |
| `0x00C8` / `0x00D8` | Squelch level, band A / B, 0–16 |
| `0x00DC` / `0x00DD` | Voice unit (FVS-2): track count of the FREE memory; flags (bit 5 LAST memory holds a recording, bit 6 FREE memory full) — `LIKELY (firmware, inferred)` |
| `0x00EB` bit 6 / bit 2 | Voice LANGUAGE / Voice RX MUTE |
| `0x00F9` bit 1 | Bluetooth on/off |
| `0x00FB` bit 0 | Voice PLAY/REC mode: 0 FREE (5 min), 1 LAST (30 s) |
| `0x02EC`–`0x02F7` | Last selected SET-menu item per category (12 bytes) |

The offsets come from the MAIN RAM mirrors (EE = RAM − `0x39752` for the state block, RAM
`0x3006C` for `0x02EC`). Evidence: `<RE-repo>/docs/notes/main_rB.md`, `main_rE.md`,
`main_rF.md`.

The compact **SET menu** the user cares about is `0x00A0`–`0x00FF` (+ a few items in
`0x0240`–`0x02FF`). Per-VFO A/B settings live in **mirror blocks at `0x00C0` (A) / `0x00D0`
(B)** (15/16 identical → same field at same offset in each).

### Decoded SET-menu items (from exp_SM1, 9-item batch)

exp_SM1 changed nine menu items at once, so its capture *located* nine bytes. The firmware's
menu-handler table pairs each of them to its item, and every changed byte fits that pairing.

| Offset | Item | Encoding | Confidence |
|---|---|---|---|
| `0x00A4` | **APO** (auto power off) | half-hours: 0 = OFF, 1–4 = 0.5–2.0 h, then 6, 8 … 24 = 3–12 h (Operating Manual, 28 APO: 1 h steps above 2 h) | `CONFIRMED` |
| `0x00C9` | **Scan Resume (A)** | 0 = BUSY, 1 = HOLD, 2 = 1 s, 3 = 3 s, 4 = 5 s (Operating Manual, 44 SCAN RESUME) | `CONFIRMED` |
| `0x00D9` | **Scan Resume (B)** | same table (A/B mirror `0xC0`/`0xD0`) | `CONFIRMED` |
| `0x00E4` / `0x00F4` | **ARS** (auto repeater shift), band A / B | bit `0x04`: 1 = AUTO (exp_SM1 cleared it on A only) | `LIKELY (firmware)` |
| `0x00EB` + `0x00FB` | **BEEP** | `0xEB` bit `0x08` with `0xFB` bit `0x10`: OFF / level 1 / level 2 | `LIKELY (firmware)` |
| `0x00AA` | **TOT** | 0 = OFF, 1–5 = 5/10/15/20/30 min, 6/7/8 = 1/2/3 min | `LIKELY (firmware)` |
| `0x028F` | **LCD DIMMER** | 3 = MAX, 5 = MID, 6 = OFF | `LIKELY (firmware)` |
| `0x02DD` | **MIC GAIN** | 0 = MIN … 2 = NORMAL … 4 = MAX | `LIKELY (firmware)` |
| `0x02DF`–`0x02E2` | **P1–P4 keys** (P3 = `0x02E1`) | `DC` OFF, `DD` 2nd PTT, `DE` SCAN, `DF` HOME CH, `E0` RPT SHIFT, `E1` REVERSE, `E2` TX POWER, `E3` SQL OFF, `E4` T-CALL, `E5` VOICE, `E6` WX, `E7` DW, `E8` PR FREQ | `LIKELY (firmware)` |
| `0x00E3` / `0x00F3` | **VFO AUTO STEP**, band A / B | bit `0x08`: the `26 STEP` editor sets it on AUTO (its default) and clears it on a fixed step; it also selects the alternate snapping tables | `LIKELY (firmware)` |

The firmware maps about 40 more menu items in `0x00A4`–`0x00FE` and `0x0280`–`0x02E2`; they
are not in this spec until a capture confirms them.

### SET-menu changes, CLNFTM15006→07 — partly paired

Changed alongside a VFO B retune:
`0xB9` 00→02, `0xBA` 0b→00, `0xBF` 02→08, `0xC3` 03→c7, `0xD0` 00→01, `0xD3` 04→14,
`0xDA` 00→01, `0xE2` 04→08, `0xE7` 03→01, `0xE9` 90→d0. Operator recollection: **SQL TYP**
(TONE ENC ↔ TONE SQL) and/or **TONE SQL FREQ** (set to 91.5 Hz; prior value unknown) were
changed. Not paired to bytes — needs single-variable captures. The firmware's state map explains
some of the others: `0xD0` band B mode, `0xDA` band B previous mode, `0xE2` band flags, and `0xE9`
bit 6 = which band is the main band (`90`→`d0` sets it) — `LIKELY (firmware)`. The later
naming pass explains three more: `0xB9`/`0xBA` are the band A/B volume and `0xBF` the selected
soft-key slot (table above) — `LIKELY (firmware)`. `0xE7` remains unpaired.

Not VFO-page fields: ADMS-17's VFO A/B pages for CLNFTM15007 match the §8 VFO decode on all
8 band rows (rx/tx/offset/direction/mode/tone/CTCSS), and the only VFO change (VFO B VHF
retune) sits in the VFO B record.

**`0xC3` (A) / `0xD3` (B) = current memory channel, 0-based — `CONFIRMED`** (same offset in
the A/B mirror blocks). Predicted then verified: selecting A = memory 009, B = memory 101 and
saving (CLNFTM15008) changed exactly `0xC3`→`08` and `0xD3`→`64`. History fits too: factory =
CH1 (only channel); 02–06 = CH4/CH5; 07 = CH200/CH21. Loading an image whose A pointed at an
empty CH200 opened A on **CH001** (radio falls back). High byte for CH257+ is
`0xC2`/`0xD2` — `LIKELY (firmware)`, unverified (all observed values < 256). The `0xD0`
`00`→`01` change in 06→07 fits band B switching from VFO to memory mode. Same capture: `0xF7` `01`→`03`,
unidentified. `0xE9`
is not a channel (factory = 07 = `d0`). The `0x02EA` sorted list is not channel references (present
in CLNFTM15000, unchanged as ~100 channels were added); `0x02EC`–`0x02F7` in it is the last
selected menu item per category — `LIKELY (firmware)`.

**Method note:** a multi-change capture *locates* the byte set quickly, but enum menu items
(unlike distinct frequencies) need the A/B-mirror structure or single-item isolation to pair.
Use small batches, and single-variable captures for stubborn enums.

## 8d. Name-present flags (`0x4CB0`) `CONFIRMED`

Evidence: [firmware-evidence.md §8d](firmware-evidence.md).

One 2-byte word per regular channel: CHn at `0x4CB0 + (n-1)*2` (CH999 ends `0x547D`).
`00 00` = the channel has a name tag, `FF FF` = no name. No other values observed.

**Evidence:** across all 7 real backups (CLNFTM15000–06) the word is `00 00`
**exactly** when the §5 name tag is non-empty — 118/118 named channels in 06, including 17
named-but-unused slots (so it tracks the *name*, not channel-in-use). Between backups the
word flips on the channel being *named*, not merely added (02→03: CH5 named, `0x4CB8`
flips). **Symptom when missing:** a generated image with correct name tags but this word
left `FF FF` showed each name in ADMS-17 as 4 square boxes. The radio loaded an image written
with the flag, and its own re-save (CLNFTM15007) kept the flags for CH200–218 (invariant holds on 07);
generated CH200–218 written with the flag display their names on the radio (`CONFIRMED`).

**What the word is** `LIKELY (firmware)`: a name layout word, read from the most
significant bit down as one code per character: `0` = 1-byte character, `10` = 2-byte
(double-byte, probably Shift-JIS) character, `11` = end of name. `00 00` is therefore "all
single-byte characters, ending at the first `FF`", and a word whose top two bits are `11` is
an empty name. The array runs on for the 100 PMS records to `0x5545` (§8b); the Home names
have their own words at `0x04D0` (§8c).

## 9. Method for future agents (how this doc gets filled in)

**Differential analysis with ADMS-17 is the primary technique.** For each unknown field:
1. In ADMS-17, load a known-good `.dat`, change **exactly one** setting to a known value,
   save as a new `.dat`.
2. `cmp -l old.dat new.dat` → the changed byte offset(s) reveal the field location.
3. Repeat with a few values to derive the encoding (linear? BCD? enum index?).
4. Record offset, size, encoding, and value mapping in this spec with a `CONFIRMED` tag.

Never promote a field to `CONFIRMED` from a single guess — require either a controlled
experiment or a doc citation.

## 10. Open questions

- Fraction codes other than `0`/`4`/`8`/`C`, incl. the air-band **8.33 kHz** channels (§7).
- Confirm `rec[12]` as the offset's high byte with an offset ≥ 12.80 MHz (§7).
- Step code `2`; the meaning of VFO, Home and PMS step codes (a VFO code 0 could mean AUTO); and confirm VFO AUTO STEP at `0xE3`/`0xF3` bit 3 on the radio (§7, §8c).
- `.FTM150` comment text encoding, and what separates a null from an empty entry (§2c).
- Remaining global **set-menu** items in `0x00A0`–`0x00FF` and `0x0240`–`0x07FF`, and the
  unpaired CLNFTM15006→07 byte `0xE7`; confirm the firmware-named bytes (§8c).
- Unknown text blocks `0x0518` / `0x7D98` (§6): written by the PC software or the factory?
- `rec[1]` bit `0x40` meaning (§7).
- Confirm on the radio that a variant mismatch in header `0x09` alone is refused, and that a restore leaves `0x0400`–`0x047F` alone (§2d).
- Confirm the per-restore write table (§2d), then align `ftm150 merge` with it.
- Squelch types 3 and 5–10 (§7) and the firmware-paired menu items (§8c).
- Band slot 4 (code 4, 850 MHz) in the VFO/Home blocks (§7, §8).
- Current-channel high byte for CH257+ (`0xC2`/`0xD2`, `LIKELY (firmware)`) and byte `0xF7` (§8c).
- Confirm the Home A/B name blocks, PMS name tags and their name words on the radio, and whether a MEMORY restore carries Home B names (§8b, §8c, §8d).
- Confirm the firmware-only regions with captures: DTMF memories, PMG list, WX names, operating-state bytes (§8c).
- Restore ownership of the shared-block records not individually marked (§2b, `LIKELY`).
- `$index.dat` slots `03`–`09` (§3).
- Confirm on the radio that `$index.dat` is stale after a backup until power-up, re-insertion
  or SD FORMAT, and the SUB clock behaviour (§3).
- Whether a PC can push a backup file to the card over USB (vendor request `0xD1`, §1).
- Radio behaviour on loading a 9–16 character tag (§5).
- ALL-only regions `0x0580`–`0x07FF`, `0x6F80`–`0x6FCF`, `0x7E00`–`0x7F3C` (§2b), and the
  constant zones `0x08000`–`0x0FFFF` / `0x144B0`–`0x17FFF` — reserved vs. fixed table (§4).

## Appendix A — reference captures

These captures (`CLNFTM150nn`, `MEMFTM150nn`, `SYSFTM150nn`) and the ADMS-17 experiment images (`exp_*`) are the operator's own and are not distributed; the names serve as evidence labels.

| File | Notes (from strings/diffs) |
|---|---|
| `CLNFTM15000.dat` | Minimal config (few/no named channels) |
| `CLNFTM15001.dat` | Adds a few named channels and Home/PMG text labels |
| `CLNFTM15002.dat` | Similar to 01 |
| `CLNFTM15003.dat` | More named repeater channels |
| `CLNFTM15004.dat` | Repeaters + full `CB CH1..80` UHF-CB bank; populated `0x0518`/`0x7D98` text blocks (role `UNKNOWN`, see §6) |
| `CLNFTM15005.dat` | Large repeater + CB set |
| `CLNFTM15006.dat` | Largest/most-populated config |
| `CLNFTM15007.dat` | Radio re-save after loading generated CH200–218; 15 channels set to name display; SET-menu changes (§8c) |
| `CLNFTM15008.dat` | 07 with A = memory 009, B = memory 101 selected (§8c) |
| `CLNFTM15009.dat` | ALL backup taken back-to-back with `MEMFTM15000` / `SYSFTM15000` (§2b) |
| `SYSFTM15000.dat` | SETUP backup (§2b) |
| `$index.dat` | Index, all-zero state (§3) |

`MEMFTM15000.dat` is the matching MEMORY backup (§2b).

All files are byte-for-byte captures.
