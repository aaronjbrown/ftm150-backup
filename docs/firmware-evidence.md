# FTM-150 backup format — firmware evidence

This appendix holds the firmware evidence behind the `LIKELY (firmware)` statements in
[`FTM-150-clone-format-spec.md`](FTM-150-clone-format-spec.md). It is organised by spec
section: evidence §n backs spec §n.

**Source.** A static analysis of the radio's MAIN firmware (`FTM-150_MAIN_EXP_V0103`, Renesas
RX, big-endian) and SUB firmware (`FTM-150_SUB_V0102`, RX, little-endian). It covers a
firmware-derived format description with a review round, and topic notes on the backup
content, the settings memory map, the SET-menu map, the settings write-back, the MAIN↔SUB link,
the SUB SD writer and the dealer codes. Nothing here has been tried on a radio unless the spec
says so. Values from the owner's radio are not reproduced; where a structural fact was checked
against a real backup, it says so.

**Citations.** `MAIN fffad635` and `SUB ffe6796e` are code addresses in the MAIN and SUB
images; `ROM 0xFFF8xxxx` is MAIN ROM data. `<RE-repo>/docs/notes/<file>.md` names the
reverse-engineering note that has the detail. These are placeholders until that repository is
published.

**Tags.**

| Tag | Meaning | Spec status word |
|---|---|---|
| **C** | Seen directly in code or ROM data | `LIKELY (firmware)` (`CONFIRMED` only once a capture or radio test proves it) |
| **I** | Inferred from the code | `LIKELY (firmware, inferred)` or `PARTIAL` |

---

## 1. Overview

| Claim | Evidence | Tag |
|---|---|---|
| The BACKUP menu offers WRITE TO SD / READ FROM SD, then the type ALL / MEM / SYS; the cursor becomes the mode byte `[0x395D4]` (0 ALL, 1 MEM, 2 SYS) | MAIN `fffb3dae` (SET item 46 handler, table ROM `0xFFF85DDC`), `fffb3eb2` | C |
| The slot name is picked from a table (`CLN`/`MEM`/`SYS` × `00`–`09`): MAIN shifts its RAM copy of the index down one entry, then takes the first of the ten names not used by entries 1–9, so a name is reused only when all others are in use | MAIN `fffac3bb`, ROM `0xFFF83A9E` | C |
| Folders: `FTM150\BACKUP` for ALL and SYS, `FTM150_MEMORY-CH` for MEM; SUB creates them (and `QSOLOG`) when it rebuilds the index | SUB `ffe6667b`, string table `FFE37414` | C |
| A restore that succeeds ends with a software reset of the radio | MAIN `fffb4a9c` → `fffb4ad8` | C |
| **USB path to the card.** Vendor request `0xD1` (accepted only while `[0xAB17]` = 1, set by MAIN) arms a bulk-OUT transfer of up to `0x19000` bytes into external RAM `0x070E1000`, length in `[0x5A1D8]`; `0xD2` ends it. SD job type 4 / op `0x12` (`sd_job_write_extbuf`) writes exactly that buffer and length to a file | SUB `ffe70cf1`–`ffe7195f` (USB0), callbacks `ffe41728`/`ffe4173e` | C (shared buffer), I (end-to-end; callbacks not traced) |

Notes: `<RE-repo>/docs/notes/main_backup_content.md`, `sub_rS2.md`.

## 2. The clone image — top level

| Claim | Evidence | Tag |
|---|---|---|
| ALL file = 128-byte header, then EEPROM0 `0x0080`–`0xFFFF`, then EEPROM1 `0x0000`–`0x7FFF`: 1 + 127 + 64 groups of `0x200` = `0x18000` bytes. EEPROM0 `0x0000`–`0x007F` is never backed up | MAIN `fffadc4d` (first group), `fffad8d2` (later groups; 16-bit address wrap at `fffadb3f` switches to device 1) | C |
| MAIN sends 512-byte groups (four 128-byte blocks) as 8 × 64-byte hex-ASCII chunks; no block address, no per-block sum, offset field 0 | MAIN `fffac109`, `fffac679`, `fffa7025`, `fffa6a53` | C |
| SUB decodes the hex and `fwrite`s each payload in arrival order: op 5 creates the file (`"w"`) and writes chunk 0, op 6 appends, op `0x11` closes. Nothing is added before, between or after | SUB `ffe40678`, `ffe6861a`, `ffe688b4` → `ffe68d8d` → `ffe6b916` | C |
| The two address spaces are I2C device-select `0xA0` (EEPROM0) and `0xA2` (EEPROM1), bit-banged by MAIN; this is not RX data flash — neither CPU programs its own flash | MAIN `fff97e34`/`fff97e40` (device 0), `fff97eb1`/`fff97ebd` (device 1); flash-register scan of both images | C |
| **One part, not two.** Probably a single 1 Mbit EEPROM with 256-byte pages (AT24CM01 / M24M01 style), with A16 in control-byte bit 1. Two 24xx512 parts (128-byte pages) fit badly: the WX-name write sends 180 bytes in one page-write cycle from `0x6800`, crossing `0x6880` | MAIN `ee_write_wx_names` `fff97f4a` → `fff97f92` | I |
| Big-endian multi-byte values (MAIN is big-endian): the offset encoder writes `+0xC` (high byte) before `+0xD`, and the current channel is a u16 at `0x00C2`–`0x00C3` | MAIN `mem_offset_from_bcd` `fff8fb37`, `mem_offset_to_bcd` `fff8faef` | C |
| No checksum or CRC over any EEPROM block, in the driver or at boot; the only sum is the header sum8 | MAIN EEPROM driver `fff96bec`–`fff98180` (no sum in any transfer routine), boot load `ee_load_all_at_boot` `fff983f8`, restore check `fffadf1d` (sums the header only) | C (absence in the code reviewed) |
| **Cable clone is a different format**: 131-byte packets `[u16 addr][128 data][sum8]`, ACK `0x06`, on SCI1. They never reach the SD file. Clone also skips `0x0400`–`0x047F` (sends `0x0400` → jumps to `0x0480`; a received `0x0400` packet is neither written nor ACKed) | MAIN `fffae7da` (receive), `fffaea80` (send), `fffaec33` (clone header, same layout as the SD header) | C |

Notes: `<RE-repo>/docs/notes/main_backup_content.md`, `link_protocol.md`, `sub_sd_writer.md`,
`settings_memory_map.md`.

## 2b. Partial backups: MEMORY and SETUP

| Claim | Evidence | Tag |
|---|---|---|
| MEM (mode 1): header, EEPROM0 `0x0180`, `0x0200`, `0x0480` (128 B each, in that file order), then `0x0800`–`0x61FF`, then EEPROM1 `0x0000`–`0x45FF` = `0xA200` bytes, into `FTM150_MEMORY-CH` | MAIN `fffadc4d` (reads `0x480` first into the third buffer), `fffad8d2` | C |
| SYS (mode 2): header, EEPROM0 `0x0080`, `0x0100`, `0x0180`, then one group `0x0280`, `0x0500`, `0x6800`, `0x6880` = `0x400` bytes, into `FTM150\BACKUP` | MAIN `fffad8f9`–`fffad9e5` | C |
| MEM compares only the first 6 magic bytes on restore and adds byte 6 to the sum; ALL and SYS compare all 7 | MAIN `fffadf1d` | C |

These layouts agree with spec §2b, which was verified byte-exact against back-to-back captures.

## 2c. ADMS-17 `.FTM150` file

The firmware never reads a `.FTM150` file. The one firmware point used in spec §2c: the
ADMS-17 blank template's header `01 04 5F` fails the restore check on the variant byte alone
(`0x0A` is summed, never compared), and the template's different `0x0400`–`0x047F` block
cannot be the cause because no restore writes that block (§2d).

## 2d. Header and restore

**Header** (built by MAIN `fffadc4d` in a zeroed buffer at RAM `0x33800`) — C:

| Offset | Source | Evidence |
|---|---|---|
| `0x00`–`0x06` | `AH086$\0` from ROM `0xFFF83C7E` | MAIN `fffadc4d` |
| `0x08` | EEPROM0 `0x047F` (market) via RAM `0x393D4` | MAIN `fff97943` |
| `0x09` | EEPROM0 `0x047D` bits 0–3 (variant) via RAM `0x3942D`; bit 7 kept apart | MAIN `fff978a9` |
| `0x0A` | ROM `0xFFF807F8` = first byte of the version `01 00 00 03` (V1.03) | MAIN `fffadc4d`; the same 4 bytes are the PC-link version reply, MAIN `fffad22f` |
| `0x7F` | sum8 of `0x00`–`0x7E` | MAIN `fffadc4d` |

**Restore check** (MAIN `fffadf1d`, sum at `fffadfdb`–`fffae035`) — C: magic; `+0x08` = own
market; `+0x09` = own variant; `(hdr[0..6] + hdr[8] + hdr[9] + hdr[0x0A]) & 0xFF == hdr[0x7F]`.
`0x0A` is loaded (`fffae01e`) but never compared. A failure sets the error flag and shows message
`0x1B`.

**What each restore writes** — C (MAIN `fffadf1d`):

| Mode | Writes | Detail |
|---|---|---|
| ALL | EEPROM0 `0x0000`–`0x03FF` (the header goes to `0x0000`, `fffae576`–`fffae59c`), `0x0480`–`0xFFFF`; EEPROM1 `0x0000`–`0x7FFF` | 128-byte page writes; when the address is `0x400` the first block is skipped |
| MEMORY | `0x01A0`–`0x01FF`, `0x0200`–`0x023F`, `0x0480`–`0x04CF`, `0x0800`–`0x61FF`; EEPROM1 `0x0000`–`0x45FF` | 16-byte loops at `fffae223`–`fffae277`, `fffae279`–`fffae2cd`, `fffae2cf`–`fffae323`; stops at `CMP #0x4D0`, then `MOV.W #0x800` at `fffae32d`. Nothing writes `0x0240`–`0x027F`, `0x03B0` or `0x04D0`–`0x04FF` |
| SETUP | `0x0080`–`0x019F`, `0x0280`–`0x02FF`, `0x0500`–`0x057F`, `0x6800`–`0x687F`, `0x6880`–`0x68B3` (52 bytes) | `0x68B3` write via MAIN `fff97e7c` |

These match the experiment in spec §2b: MEMORY applies Home A slot 1 and Home B slot 0, SETUP
applies VFO B slot 3.

**Identity block `0x0400`–`0x047F`** — every MAIN accessor with an address in this range:

| EE | Accessor | Use | Tag |
|---|---|---|---|
| `0x0400`–`0x045F` | MAIN `fff97f03` (read `fff97eeb`, write `fff97ef7`), RAM `0x30328` | RF alignment (BPF tuning, TX power drive, deviation, S-meter, squelch, battery and DAC calibration, IF-chip register). Read once at boot; set from ROM `0xFFF820E0` on a full reset; written only by the service adjust handlers `fffa5964`…`fffa5f0f` (each steps one byte ±1) and `fff9c1c8` | C ("alignment" I) |
| `0x0460`–`0x0477` | none | Only the bulk backup touches it | C |
| `0x0478`–`0x047C` | MAIN `fff9798e`, read only | 5-character ID; read at boot, bytes outside `0-9A-Za-z` become `*`; nothing in MAIN writes it | C (meaning unknown) |
| `0x047D` | MAIN `fff978a9` | Variant (bits 0–3) and the strap value at the last save (bit 7) | C |
| `0x047E` | MAIN `fff9790a` | Layout stamp from ROM `0xFFF807FC`; written only on a full reset | C (meaning I) |
| `0x047F` | MAIN `fff97943` | Market, written only from ROM `0xFFF807FD` (full reset, wrong-market recovery) | C |

**Who can change the identity block.** No restore mode and no clone writes it. The variant
changes only through the PC link (MAIN `fffad7af`, EXP firmware only, value ≤ 15) or the
front-panel dealer-code variant editor (MAIN `fff94eb5` matches key sequences from ROM
`0xFFF80854`; the editor saves to `0x047D` at `fff9e5d4`); a service-mode dealer code enters the
alignment adjust mode. Because a restore never writes the block, restoring a backup does not
undo a variant or alignment change, and loading another radio's file does not change this
radio's alignment — C. Boot checks: `EE[0x47F]` ≠ ROM market locks the radio in a "wrong
market" loop until a recovery key sequence re-stamps it (MAIN `fff90069`, `fff902ff`,
`fff94eb5`); an invalid variant also locks (MAIN `fff99298`) — C.

**PC raw EEPROM command.** PC cmd `0xF3` (MAIN `fffad5c0`) reads and PC cmd `0xF4` (MAIN
`fffad635`) writes 64 bytes at an address from the frame. The write NAKs (`0x15`, MAIN
`fffacde8`) any start address with `0x400 ≤ addr < 0x480` (MAIN `fffad651`–`fffad65d`) — C.
Only the start address is checked; a 64-byte poke from `0x3C1`–`0x3FF` is one I2C page write
(MAIN `fff97ded`) and `0x400` is a page boundary, so it wraps within its page — I. (An earlier
version of the analysis said the poke could write any address; that was corrected
2026-11-14.) Side note: the raw peek/poke end with a plain I2C stop rather than the driver's
finish routine, which leaves the "EE busy" flag set; a later power fail would then skip its
immediate state save — I.

**A second raw write has no guard.** PC cmd `0xF1` (MAIN `pccmd_f1_ee_write_bytes` `fffad4e8`)
writes 2 bytes to EEPROM0 at a 16-bit address taken from the frame (`0x37BA0`/`0x37BA1` →
`0x39AA4`/`0x39AA5`, data from `0x37BA2`/`0x37BA3`), then sends ACK (`fffacdfe`). The routine
(`fffad4e8`–`fffad589`) has no compare on the address, so this command can write
`0x0400`–`0x047F` — C (from the disassembly; read during this reconciliation, not in the
analysis notes). PC cmd `0xF0` (`fffad415`) is the matching 1-byte read. These two are the
"raw peek and poke" of the side note above (they end with `i2c_stop` `fff981ac`). Spec §2d
states the consequence: the identity block is out of reach of every file and of the 64-byte
command, but not of the PC link as a whole.

**After a restore: boot fix-ups** (MAIN `ee_load_all_at_boot`) — C (meaning of the second I):
- ID bytes outside `0-9`/`A-Z`/`a-z` at `0x0478`–`0x047C` become `*`. A restore never writes
  the ID (it is in `0x0400`–`0x047F`), so this acts on the radio's own ID, not on a file's.
- A VFO record for band slot 2 (174–400 MHz) that holds `01 74 00` (174.000 MHz) in its
  `+2..+4` gets `+2` = `0x81` (174.005 MHz) when it is read; the VFO block offsets are `0x22`–`0x24`
  (MAIN `ee_read_vfo_record` `fff97307`, called from the boot load `fff983f8`). A migration
  fix-up — C (meaning I).
- An image whose init magic `0x00FF` is not `AA` (valid) or `55` (soft reset) triggers a full
  init at boot (`boot_factory_reset` MAIN `fff991e3`); a file with `FF` there would probably
  reset the radio — I.

**Card and power loss** (SUB):
- The file system is a POSIX/stdio-style FAT library (`fopen` modes `"r" "w" "a" "r+"`), not
  ChaN FatFs — C. Every allocation, count, find and format path branches only on FAT12/16/32;
  exFAT has detection but no allocator — C (code paths), I (that an exFAT card is unusable).
- The `LMREPAIR` journal (4 × 512 B on the card) logs directory metadata only; replay at mount
  trims a file to its cluster chain. A power cut during a backup therefore leaves a short file,
  which the index rebuild ignores because of its exact-size filter (§3) — C (journal), I
  (outcome). The journal reset path never runs (its enable byte has no writer) — C.
- On restore SUB only checks that each `fread` returns the full length; a truncated file fails at
  its first short read — C (check), I (outcome). All content checks are MAIN's.

Notes: `<RE-repo>/docs/notes/main_backup_content.md`, `dealer_codes.md`, `link_protocol.md`,
`main_rA.md`, `main_rB.md`, `main_rD.md`, `settings_memory_map.md`, `sub_rS1.md`,
`sub_sd_writer.md`.

## 2e. Not in any backup

| Claim | Evidence | Tag |
|---|---|---|
| Bluetooth paired-device list: RAM `0x303C8`, 8 × 28 B (name, hex address; `FF` = empty), cleared at boot; no EEPROM address. Only BT on/off (`0x00F9` bit 1) and a sub-item bit (`0x00F9` bit 0) are stored | MAIN `fff98fe2` (clear), `fffb41f3` (BT menu), `bt_dev_list_insert` | C (the list probably mirrors SUB-side data, I) |
| Voice recordings live in the FVS-2 unit; MAIN stores only the track count and flags (`0x00DC`/`0x00DD`) | MAIN `fffaee26`–`fffaf014` | C |
| The SUB voice recorder writes RIFF/WAVE files (PCM, mono, 16 kHz, 16-bit, 44-byte header) with its own recovery journal `I:\RECBACKUP`; unrelated to the backup files | SUB `ffe6a7b4`–`ffe6b2b6`, `ffe6ccf9`–`ffe6e53c` | C |

Notes: `<RE-repo>/docs/notes/main_rE.md`, `main_rF.md`, `sub_rS2.md`, `sub_sd_writer.md`.

## 3. `$index.dat`

| Claim | Evidence | Tag |
|---|---|---|
| SUB writes it; MAIN only reads it (op `0x0D` 0x200 bytes, op `0x0C` 0xD0 bytes, op `0x11`) into RAM `0x3722C`, and never writes it back | SUB `ffe6667b`; MAIN `fffac6f3`, `fffac791`, `fffac8fd` | C |
| Rebuild: remove and recreate as 720 zero bytes; scan `FTM150\BACKUP` (up to 50 entries) and `FTM150_MEMORY-CH`; classify **by size only** (`0x18000` at SUB `ffe67008`, `0x400` at `ffe6769f`, `0xA200` at `ffe67d6f`); fill each section with up to 10 entries newest first | SUB `ffe6667b` | C |
| Entry: 6 BCD bytes `YY(−2000) MM DD hh mm ss`, 16-byte name without `.dat` NUL-padded, 2 × `00` (spec: the name field NUL-padded to 18 B — the same bytes) | SUB `ffe6b610`; MAIN `fffac3bb` (`MUL #0xF0` / `#0x18`) | C |
| Rejected: stat failed; wrong size; first character not `[0-9A-Za-z]` or any of the first 13 characters outside `0x20`–`0x7E`; no `.DAT` (any case) within the first 13 characters. The `CLN`/`SYS` prefix is not checked | SUB `ffe6834e`, `ffe683c9` | C |
| Files dated before 2000 are skipped (`tm_year > 99`), and an all-zero date never sorts in (strict `>` against 0) | SUB `ffe6667b` | C |
| **Rebuild triggers.** Exactly three call sites: op `0x73` (SUB `ffe68b16`); card-mount edge (SUB `ffe6b43c`, `[0xE1E2]` 0→1, set by the card-detect poll `ffe610da` at power-up or insertion); `[0x9239]==3` (SUB `ffe6b534`), dead code since `[0x9239]` is only ever set to 4 or 0. The write path (ops 5/6/`0x11`) never reaches the rebuild | SUB disassembly, `BSR.W 0xffe6667b` | C |
| MAIN requests op `0x73` only from SD FORMAT: SET item 48 handler MAIN `fffb40ca` sends op `0x50` (format) and then `0x73`; the sole write of link request `0x08` is at MAIN `fffb4153`; every other write of `[0x38164]` stores 0, 2, `0x80` or `0x42`. These two ops have no timeout | MAIN `fffb40ca`, `fffb4153`, `fffac5bf`/`fffac5d0`, ack `fffac63f` | C |
| **Therefore the card's `$index.dat` is stale after a backup** until the next power-up, re-insertion or SD FORMAT; meanwhile MAIN lists the new backup from its RAM copy, which `fffac3bb` updated | above | C |
| **SUB clock.** Software only (5 ms tick `ffe8cd3c`), set to 2024-06-01 00:00 at every boot (`ffe8cd63`). The only other setter is the index rebuild: running 64-bit maximum of the timestamps (SUB `ffe6796e`–`ffe679ae`), then `clk_set_bcd_if_valid` (SUB `ffe68222`). FAT timestamps come from the tm buffer the clock publishes (`*[0x20764]`) | SUB `clk_tick` `ffe8cd3c`, `clk_init_default` `ffe8cd63` (called from init `ffe71990`), `clk_set_bcd_if_valid` `ffe8cd74` / `clk_set_bcd` `ffe8cd99`, `clk_publish` `ffe8cf27`, rebuild `ffe6667b` | C (mechanism), I (that the maximum is the FAT write time) |
| Consequence: newest-first order holds, and a radio-made backup is never dated before 2000 | above | I |

Notes: `<RE-repo>/docs/notes/sub_sd_writer.md` (§5, §9), `link_protocol.md`, `main_backup_content.md`.

## 4. High-level memory map

| Claim | Evidence | Tag |
|---|---|---|
| `0x0080`–`0x009F`: band A / B current records, flushed to EEPROM right before a backup | MAIN `fff981e3` (state save), `fffadc4d` | C |
| `0x0080`–`0x00FF` is the only write-back block: it lives in RAM and is saved in one 128-byte transfer at power-off, power fail, MEMORY CH RESET, reset/init, and SD/clone backup or restore. Everything else is written through when it changes | MAIN `fff981e3` and its callers, `isr_power_fail` `fff8fd7a` | C |
| `0x0400`–`0x047F`: identity and alignment (§2d) | MAIN `fff97f03`, `fff9798e`, `fff978a9`, `fff9790a`, `fff97943` (table in §2d) | C |
| `0x0800`–`0x4CAF`: 1 099 records = 999 regular + 100 PMS; `0x4CB0`–`0x5545`: their name words | MAIN `ee_access_edit_record` `fff9761d` (`0x800 + 16n`), `ee_load_chan_used_cache` `fff98692` (n < 1099), `ee_access_edit_layout` `fff97b45` (`0x4CB0 + 2n`), `mem_find_next_used` `fffa3406` (wrap at 1098) | C |
| `0x5600`–`0x564F`: PMG list; `0x6800`–`0x689F` WX names, `0x68A0`–`0x68B3` their words | MAIN `ee_access_pmg` `fff97dcb` (80 B at `0x5600`), `ee_access_wx_names` `fff97f56` (180 B at `0x6800`, `ee_xfer180` `fff97f92`) | C |
| `0x0500`–`0x057F`, `0x0580`–`0x07FF`, `0x6F80`–`0x6FCF`, `0x7C00`–`0x7F3F`, `0x8000`–`0xFFFF` and EEPROM1 `0x44B0`–`0x7FFF`: no address constant anywhere in MAIN; only bulk backup/restore and the PC raw peek/poke reach them | MAIN disassembly scan; MAIN `fffad5c0`/`fffad635` | C (absence), I (owner: PC software or factory) |
| EEPROM1 `0x0000`–`0x44AF`: 1 099 names × 16 B | MAIN `ee_access_edit_name` `fff97aca` (A2: `16n`), `mem_find_used_from_index` `fffa57ea` (to 1099) | C |

Notes: `<RE-repo>/docs/notes/settings_memory_map.md`, `settings_writeback.md`.

## 5. Name tags

| Claim | Evidence | Tag |
|---|---|---|
| Names are ASCII, not the LCD font (the display maps ASCII through ROM `0xFFF827AF`); any byte ≥ `0xF0` ends a name; `FF` in byte 0 = no name | MAIN `char_ascii_to_radio` `fff96abb`, `disp_expand_text_cells` `fffa9068` (stops at codes ≥ `0xF0`), `ee_access_band_mem_name` `fff97bb5` (no channel → 16 × `FF`) | C |
| The array has 1 099 entries: the 100 PMS records follow the 999 regular ones (`0x13E70`–`0x144AF`) | MAIN `ee_access_band_mem_name` `fff97bb5` (n from the band channel or a PMG link), `fffa57ea` (index to 1099) | C |

## 6. Unknown text blocks at `0x0518` / `0x7D98`

MAIN has no functional accessor for `0x0500`–`0x07FF` or `0x7C00`–`0x7F3F` (no address constant
in the disassembly). `0x0500`–`0x057F` is touched only by SYS/ALL block I/O (MAIN `fffad8d2`,
`fffadf1d`) and the PC raw peek/poke (MAIN `fffad5c0`/`fffad635`) — C. Who owns them (PC
software or factory) is I.

## 7. Memory-channel record

Codec: decoders MAIN `fff8706f` / `fff870d9` / `fff871ad`, encoder MAIN `fff8837f`. The same
16-byte format is used for memory channels, VFOs, Home channels, the current A/B records and
inline PMG entries — C.

| Field | Firmware evidence | Tag |
|---|---|---|
| `+0` bit 7 in use (0 = hidden, data kept); bits 0–2 band; bit 3 M-GRP; bit 5 SCAN skip | decoder `band_load_rec_fields` `fff8706f`, `ee_load_chan_used_cache` `fff98692` (bit 7 per record), `mem_find_next_in_band` `fffa32cc` (band bits, M-GRP bit 3), `mem_step_next_used` `fffa4251` (bit 5 in skip scan); hidden-but-kept was checked against a real backup | C |
| `+0` bit 4 | When set, the decoder clears `+1` bit 5; cleared when a VFO is stored | C (meaning unknown) |
| `+1` bit 3 reverse | The encoder does not save the working record while it is set | I |
| `+1` bit 6 | No reader found in MAIN (decoders `fff8706f`/`fff870d9`/`fff871ad` do not test it); an absence, so no address proves it | I |
| `+2`/`+6` high nibble: fraction codes `0 2 3 4 5 6 8 A B C D E` | Step-snapping encoder MAIN `fff875bc` and its ROM tables: 6.25/12.5 kHz `0xFFF8039E` (`0 2 4 6 8 A C E`), 8.33 kHz `0xFFF8048E` (`0 3 5 8 B D`), alternate 12.5 kHz `0xFFF803EE` (`0 4 8 C`), alternate 25 kHz `0xFFF8043E` (`0 8`); 5/10/15/20 kHz mask to `0`/`8`; 25/50/100 kHz leave the nibble alone | C |
| `+5` high nibble: squelch type list `0 OFF, 1 TONE ENC, 2 TONE SQL, 3 REV TONE, 4 DCS, 5 PR FREQ, 6 PAGER, 7 DCS ENC, 8 TONE DCS, 9 DCS TSQL, 10 JR FREQ` | Menu list ROM `0xFFF84898`; the SQL TYPE editor MAIN `fffb34ce` offers 0–6 with SQL EXPANSION off, 0–9 with it on, and 10 only for variants 13–15 (region low nibble > `0xC`); 11 is unreachable | C (0/1/2/4 and the gating), I (labels of 3, 5–10 from list order) |
| `+5` low nibble: step index `0 5, 1 6.25, 2 8.33, 3 10, 4 12.5, 5 15, 6 20, 7 25, 8 50, 9 100 kHz` | Labels ROM `0xFFF846BE`; per-band allowed steps ROM `0xFFF83CB9` / `0xFFF83CF0` | C (1, 2, 4 via the snapping tables), I (others) |
| `+9` bits 0–5 CTCSS index (labels ROM `0xFFF83F33`), bits 6–7 power (HIGH/MED/LOW; drive table RAM `0x30332`) | MAIN `tone_search_step_ctcss` `fffa514b` (steps `+9` bits 0–5 over 0–49), TX POWER editor `fffb1fbc` (`+9` bits 6–7), alignment handler `fffa5ac1` (`0x30332[power level]`) | C |
| `+10` bits 0–6 DCS index (labels ROM `0xFFF83D8F`), bit 7 Clock Shift (CLOCK TYPE editor MAIN `fffb2e6d`) | MAIN `menu_tone_sql_freq_change` `fffb3688` (`+10` bits 0–6), `fffb2e6d` | C |
| `+11` bits 0–4 User CTCSS (PR FREQUENCY editor MAIN `fffb3ad2`); masked `& 0x1F`; ROM `0xFFF85888[v]` = 0.3 × (100·v Hz) for v = 3…30 | MAIN `menu_pr_frequency_change` `fffb3ad2`, ROM `0xFFF85888` | C |
| `+12..+13`: repeater offset as one big-endian u16 of 50 kHz units; the RPT SHIFT FREQ editor steps 0.00–99.95 MHz (`CMP #0x9994` at MAIN `fffb2ad9`), so 0–1999 | Editor MAIN `fffb2abf`, encoder `fff8fb37` (writes `+0xC` then `+0xD`), decoder `fff8faef` | C |

Not repeated here: the experiment-backed decodes in spec §7, which the firmware agrees with.

## 8. VFO / Home records

| Claim | Evidence | Tag |
|---|---|---|
| `0x00C0`/`0x00D0` band mode 2 is the mode that uses the `0x01A0`/`0x01F0` records, so those blocks are Home | MAIN `fff9743a` | C |
| VFO band table AIR 108–137, 137–174, 174–400, 400–470, code 4 = 470+ (slot 4 default 850.000 MHz); memories put 476–477 MHz in code 3 | MAIN band tables; code-3 range checked against a real backup | C (table), I (ranges for memories) |
| `0x00E3`/`0x00F3` bit 3 = VFO AUTO STEP: in VFO mode the STEP editor treats index 10 as AUTO, sets the bit (`BSET` at MAIN `fffb2e1f`) and stores the computed step; a fixed step clears it (`BCLR` at `fffb2e0e`). It also selects the alternate snapping tables | MAIN `fffb2d46`, `fff875bc` | C |

## 8b. PMS and Home tags

| Claim | Evidence | Tag |
|---|---|---|
| PMS record *k* (0–99) has its name at `0x13E70 + 16·k` and its word at `0x547E + 2·k` (index n = 999 + k in the shared arrays) | MAIN `ee_access_edit_name` `fff97aca` (A2: `16n`), `ee_access_edit_layout` `fff97b45` (`0x4CB0 + 2n`), `memlist_step_10` `fffa0857` (index up to `0x44A`) | C |
| Home names: Home A `0x0480`–`0x04CF`, Home B `0x03B0`–`0x03FF`; words: Home A `0x04D0`–`0x04D9`, a 6-byte gap, Home B `0x04E0`–`0x04E9` | MAIN `fff97a50` | C |

## 8c. SET-menu and settings

The 64 SET items each have a change handler in ROM table `0xFFF85DDC` (display handlers at
`0xFFF861DC`). Band B = band A + `0x10`. The defaults were checked against a real backup — C
unless marked.

**Operating-state block `0x00A0`–`0x00FF`** (RAM `0x397F2`–`0x39851`; EE = RAM − `0x39752`):

| EE | Item | Handler / reader |
|---|---|---|
| `0xA0` | Region byte: `0x30` + variant for variants 0–10 (11 → `0x0B`, 12–15 → `0x3C`–`0x3F`); low nibble = variant, bit 4 per-band VFO default flag, bit 5 unknown | MAIN `fff99298`, ROM `0xFFF808C4` |
| `0xA4` | APO, half-hours | `fffb2e9e` |
| `0xA6` | DATA BAND 0–3 | `fffb3d4c` |
| `0xA9` | Voice VOLUME 0–2 (also sent to the voice unit, cmd `0x85`) | `fffb457e`, `vu_queue_volume` |
| `0xAA` | TOT | `fffb22eb` |
| `0xAE` | Voice ANNOUNCE 0 OFF, 1 MANUAL, 2 AUTO | `fffb457e`, `dtmf_edit_put_digit` |
| `0xB2` | S-METER SYMBOL 0–3 | `fffb1f42` |
| `0xB3` bit 7, `0xB6`, `0xB7` | VOX MIC, VOX, VOX DELAY | `fffb21c2` |
| `0xB9` / `0xBA` | Volume 0–31 (knob; saved with the state block) | MAIN volume/squelch knob handler (RAM `0x3980B`/`0x3980C`) |
| `0xBB`, `0xBC` | LCD CONTRAST 1–9, BACKLIGHT COLOR | `fffb1e1b`, `fffb1f88` |
| `0xBE` | Current SET-menu category 0–11 | `menu_category_step`, `menu_enter_setmode` |
| `0xBF` | Selected soft-key slot | `softkey_assign_slot`, `menu_enter_softkey_mode` |
| `0xC0` / `0xD0` | Band mode: 0 VFO, 1 memory, 2 Home | `fff9743a` |
| `0xC2`–`0xC3` / `0xD2`–`0xD3` | Current memory channel, u16 BE, 0-based (RAM `0x39814` / `0x39824`) | `ee_access_band_mem_record` `fff9768c`, `memlist_open` `fff9e6f1` |
| `0xC4` / `0xD4`, `0xC7` / `0xD7` | VFO band; DTMF slot | DTMF editor `fffb2f9b` |
| `0xC8` / `0xD8` | Squelch level 0–16 (knob in SQL-adjust mode) | RAM `0x3981A`/`0x3982A` |
| `0xC9` / `0xD9` | SCAN RESUME | `fffb3cd5` |
| `0xCB` / `0xDB` | DUAL RX INTERVAL | `fffb3c3a` |
| `0xDC` / `0xDD` | FVS-2 track count; flags (bit 5 LAST has a recording, bit 6 FREE full) | `fvs_track_added`, `vu_track_ended` — I (meaning) |
| `0xE2`/`0xF2` b0, `0xE2`+`0xF2` b6 | PRIORITY REVERT; WX ALERT | `fffb3c99`, `fffb3bae` |
| `0xE3`+`0xF3` b0, `0xE3`/`0xF3` b3, b4 | SQL EXPANSION; VFO STEP AUTO; VFO RX MODE AUTO | `fffb3985`, `fffb2d46`, `fffb23c8` |
| `0xE4` / `0xF4` b2 | RPT ARS | `fffb2a07` |
| `0xE5` / `0xF5` b5 | BAND SCOPE (polarity I) | `fffb1e58` |
| `0xE8` b3, b6 | DATA SPEED; FRONT SP MUTE | `fffb3d8d`, `fffb2f41` |
| `0xE9` b0–1 | SUBBAND MUTE; bit 6 = main band | `fffb24d2` |
| `0xEB` b2 | Voice RX MUTE (inverted: shown ON when clear) | `fffb457e` |
| `0xEB` b3 + `0xFB` b4 | BEEP off / level 1 / level 2 | `fffb27c9` |
| `0xEB` b6 | Voice LANGUAGE (adds `0x50` to each voice word) | `fffb457e` |
| `0xEC` / `0xFC` | BAND SKIP mask | `menu_band_skip_change` `fffb2806`; read by `vfo_band_step` `fffa3176` |
| `0xEE` + `0xFE` | REAR SP OUT 0–10 | `fffb2ef4` |
| `0xF8` b6, `0xF9` b2, `0xF9`+`0xFA` b3 | MEMORY LIST MODE; AUTO DIALER; SUB BAND (polarity I) | `fffb2629`, `fffb22be`, `fffb24d2` |
| `0xF9` b1 | Bluetooth on/off | `fffb41f3` |
| `0xFB` b0 | Voice PLAY/REC: 0 FREE 5 min, 1 LAST 30 s | `fffb457e` |
| `0xFF` | Init magic: `AA` valid, `55` soft reset, else full init | `boot_factory_reset` `fff991e3` |

**Settings block `0x0280`–`0x02FF`** (RAM `0x30000`; defaults ROM `0xFFF82060`; written whole on
every change):

| EE | Item | Handler |
|---|---|---|
| `0x0280`–`0x0283` | Channel numbers per band, u16 (RAM `0x30000`/`0x30010`) — I | `mem_band_step` `fffa2ed4` |
| `0x028E` / `0x029E` | BELL RINGER | `fffb3b65` |
| `0x028F` | LCD DIMMER 3 / 5 / 6 | `fffb1dcf` |
| `0x02A0`–`0x02A8` | Soft-key list: menu item numbers, `FF` empty | `fffb6d01` |
| `0x02C4`, `0x02D9` | PMG HOLD, PMG TIMER | `fffb2657` |
| `0x02D2`–`0x02D5` | PAGER codes, stored as code − 1 | `fffb39a2` |
| `0x02DD` | MIC GAIN | `fffb2184` |
| `0x02DF`–`0x02E2` | P1–P4 key function codes `DC`–`E8` (labels ROM `0xFFF8503E`; defaults per region ROM `0xFFF83CAD`) | `fffb2c0b` |
| `0x02EC`–`0x02F7` | Last selected item per menu category (RAM `0x3006C`) | `menu_enter_category`, `menu_jump_to_item` |
| `0x02FE` | ROM default byte `0xFFF820DE`; no accessor; unrelated to header `0x0A` | copied only with the whole block from ROM `0xFFF82060` (`settings_load_defaults` `fff99353`) |

Other regions: DTMF memories `0x0300`–`0x038F` (digit codes ending `FF`); PMG list
`0x5600`–`0x564F` (byte 0 bit 7 used; bit 4 set → `+2..+3` = u16 channel index, else an inline
record); WX names `0x6800`. Still unmapped: bytes in `0x00A1`–`0x00BF` and `0x0280`–`0x02FF` that
no menu handler writes. Items with no stored setting (actions or screens) include BACKUP, SD
INFORMATION, SD FORMAT, CLONE TX/RX, MEMORY CH RESET and FACTORY RESET.

Notes: `<RE-repo>/docs/notes/settings_menu_map.md`, `settings_memory_map.md`, `main_rB.md`,
`main_rE.md`, `main_rF.md`.

## 8d. Name layout words

| Claim | Evidence | Tag |
|---|---|---|
| One u16 BE word per name, read from the MSB: `0` 1-byte char, `10` 2-byte char, `11` end. A name ends at the first `11` or the first byte ≥ `F0`; `(w & 0xC000) == 0xC000` = empty. A plain ASCII name has `0000` (checked against a real backup) | MAIN `disp_expand_text_cells` `fffa9068` (reads the word with the name), `disp_pack_text_cells` `fffa918a` (builds it on name edit), `ee_xfer2` `fff97847` | C |
| The double-byte set is probably JIS / Shift-JIS | No code table identified; only the 2-byte cells of `fffa9068` / `fffa918a` | I |
| Arrays: regular `0x4CB0 + 2n` (to `0x547D`), PMS `0x547E`–`0x5545`, Home A `0x04D0`, Home B `0x04E0`, WX `0x68A0` | MAIN `ee_access_edit_layout` `fff97b45` (regular and PMS), `ee_access_home_layout` `fff97a50` (Home A / B), `ee_access_wx_names` `fff97f56` (WX words in its 180-byte block) | C |

Notes: `<RE-repo>/docs/notes/settings_memory_map.md`.

## 10. Open firmware questions

- `+0` bits 4 and 6, `+1` bit 7, `+11` bits 5–6, `+14..+15` of the channel record.
- Squelch types 3 and 5–9 on the radio.
- Polarity of BAND SCOPE and SUB BAND; PMG HOLD labels.
- Owners of `0x0500`–`0x057F`, `0x7C00`–`0x7F3F` and the `CA`-filled ranges.
- The end-to-end USB → card flow (callbacks SUB `ffe41728` / `ffe4173e`).
- Which physical panel keys arm the dealer codes.
