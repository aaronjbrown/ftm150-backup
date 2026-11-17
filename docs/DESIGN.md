# ftm150 — Design

How the `ftm150` package is built and why. Written for whoever maintains or extends it
next, human or agent. The file format itself is documented in
[`FTM-150-clone-format-spec.md`](FTM-150-clone-format-spec.md); this document covers the
software around it.

## 1. Purpose and scope

`ftm150` reads and edits the SD-card backups of a Yaesu FTM-150R/E: the full ALL image
(`CLNFTM150nn.dat`) and the radio's MEMORY (`MEMFTM150nn.dat`) and SETUP
(`SYSFTM150nn.dat`) partial backups. It ships a library, a CLI (`ftm150`) and an optional
MCP server (`ftm150-mcp`).

It is the radio-config-editing part of a larger ham-radio agent. Repeater lookup and RF
line-of-sight are separate MCP servers with their own repositories; `ftm150` never imports
them. The agent hands `ftm150` a list of **RepeaterSpec** rows (a neutral, radio-agnostic
JSON contract published by the upstream repeater-lookup producer) and `ftm150` writes them
as channels onto a copy of the user's image. RepeaterSpec rows carry absolute rx/tx
frequencies, so all radio-specific encoding (band, shift, offset, tone mode) happens here.

The contract is guarded without a runtime dependency:

- `ftm150/schemas/repeater_spec.schema.json` is a hand-written, deliberately loose schema
  (decimals as string or number, most fields nullable, unknown keys allowed). The reader
  uses `dict.get` and ignores unknown keys, so a strict schema would only reject
  forward-compatible payloads.
- `tests/fixtures/upstream_repeater_spec.schema.json` is a verbatim copy of the producer's
  published schema. `tests/test_schema_contract.py` checks that the vendored schema
  declares every upstream field, requires no more than upstream, covers every upstream
  mode, and that a payload shaped like the producer's output validates against both. The fixture is a copy of
  the schema published by the repeater-lookup producer; to check for drift, replace it with
  that producer's current schema and run the test.

## 2. Layers

```
cli.py   mcp/server.py         thin adapters: parse arguments, call one ops function, format
            │
          ops.py               the single core: load -> validate all -> apply -> save
     ┌──────┼───────────────┐
 coerce.py  interop/        fileio.py      text parsing | format adapters | safe output
     └──────┼───────────────┘
          units.py             exact decimal MHz/kHz <-> int Hz at every edge
            │
          engine/              the binary format and the domain model
```

**engine/** (format and model; bytes in, bytes out. From outside `engine/` it imports
only `units`, and it opens no files: `ops` reads and writes them. `tests/test_layers.py`
enforces the imports.)

- `layout.py` — offsets and counts (record base, stride, name tags, name-present words,
  PMS, VFO/Home blocks, set-menu bytes).
- `tables.py` — code tables (CTCSS, DCS, shift, tone mode, power, step), `Band`
  (`IntEnum`, codes 0–3), `BAND_RANGES` in Hz, and `RawCode`, an `int` subclass for an
  undecoded code. `as_band` turns a `RawCode` naming a decoded band (0–3) into its `Band`.
- `fields.py` — bit-field descriptors over a 16-byte record: `Flag`, `Code` (table label
  or `RawCode`), `Indexed` (index into a value list; out-of-table reads `None`), `Freq`
  (BCD frequency in int Hz), plus `encode_freq`/`decode_freq`. The codec stays a pair of
  module functions, not `Freq` methods: a `Freq` is a location in a record, while the
  codec is a pure Hz ↔ bytes value conversion that `Channel.retune` uses
  without a descriptor.
- `record.py` — `Channel`, a view over one record (and, for regular channels, its name tag
  and name-present word); `ChannelRecord`, a frozen, format-neutral snapshot of every
  decoded field; `write_record`, the validated writer; `FIELDS`, the one list of settable
  fields.
- `settings.py` — read-only `Settings` view of the decoded set-menu items (APO, Scan
  Resume A/B); undecoded values read as the raw `int`.
- `partial.py` — `Kind` (`StrEnum`: ALL, MEMORY, SETUP; referenced only as `Kind.X`),
  `Span`, `Block`, `Layout` and
  `LAYOUTS` (size, block map and owned shared-block slice per kind), `detect_kind`,
  `expand`, `extract`, `merge_ranges`.
- `image.py` — `CloneImage` (ALL) composed of `MemoryImage` and `SetupImage` views over
  one ALL-sized buffer; `from_bytes`/`to_bytes` on each kind; `image_from_bytes`
  dispatches on size; `NotInBackup`.

**units.py** — exact conversion between decimal MHz/kHz (text or number) and int Hz, the
MHz text forms used in CSV, and `parse_step`. Stdlib only; imports nothing from the
engine.

**interop/** — pure converters between external rows and `ChannelRecord`; no file I/O.
`csv_io` (native CSV), `chirp` (CHIRP CSV), `repeater_spec` (RepeaterSpec → record, plus
the `Applied`/`Skipped`/`ApplyResult` result types), and `_common` (Duplex/Tone labels and
the Offset text rule both CSV formats share).

**coerce.py** — text parsers for the CLI/MCP `set` edge. `PARSERS` is keyed by exactly
`engine.record.FIELDS`; `EDGE_ALIASES` maps the user-facing `rx_mhz`, `tx_mhz` and
`offset_khz` to the engine's `rx_hz`, `tx_hz` and `offset_hz`; `SETTABLE` is the
user-facing field set derived from both.

**fileio.py** — `atomic_write` and `resolve_output` (the one "don't clobber an input"
rule). Only `ops` imports it. It stays its own module, not part of `ops`: it is
stdlib-only filesystem safety code with no radio knowledge and its own tests.

**ops.py** — `info`, `rows`, `set_field`, `export_csv`, `import_csv`, `apply_specs`,
`extract`, `merge`. Every command the CLI and MCP offer is one function here, so both
surfaces share one tested behaviour. It also holds the image file I/O: `load_image(path)`
and `save_image(img, path)` (atomic, with no clobber check; the commands check first).

**cli.py**, **mcp/server.py** — adapters only. The MCP server never imports the CLI
(a test enforces it). The CLI's error contract: invalid input and I/O failures
(`ValueError`, `KeyError`, `OSError`, `IndexError`) print `error: <msg>` on stderr, return 2
and write no output file. Programming errors (`TypeError`, `AttributeError`, …) are
deliberately not caught, so a bug surfaces as a traceback instead of passing for a user
error.

The MCP tools carry full type annotations because FastMCP builds each tool's JSON schema
from them; an unannotated argument is advertised as `string`, and a client sending
`channel: "5"` would hit a `TypeError` inside the engine. A test checks the generated
argument schemas.

## 3. Key decisions

### Never guess a field

A byte's meaning is accepted only from a controlled single-variable capture or a manual
citation. In code this means:

- An unknown code is read as `RawCode(n)` and written back unchanged; it is never replaced
  by a default. Native CSV writes it as its digits and imports digits back as `RawCode`.
  CHIRP export refuses any raw code, and native export refuses a raw step code, because a
  bare number in `TStep` would re-import as a kHz value. `dump` uses the same rows, so it
  refuses too: one channel with a raw step code stops native export and `dump` for the
  whole image.
- Out-of-range or off-grid values are refused, never truncated or rounded: frequencies
  off the 2.5 kHz grid (the confirmed fraction codes, spec §7) or outside the 5-digit BCD range, offsets that are not 0–12.75 MHz
  in 50 kHz steps, names longer than 8 ASCII characters (8 is the radio's entry limit, spec §5, and its handling of longer tags is unknown; a longer tag already stored in an image is kept byte-exact), tones/codes outside the
  standard tables.
- Undecoded bits (`rec[1]` `0x40`, `rec[11]` `0x60`, bytes 14, 15) and every undecoded region of the
  image are carried through byte-exact.
- A frequency whose fraction code (`rec[2]`/`rec[6]` high nibble) is not confirmed raises
  on read, like a non-BCD digit: a frequency has no raw form to fall back to, and reading
  it without the code would report a different frequency. The codec owns the whole byte,
  so a frequency write replaces the code.
- The same holds for the offset: a non-zero `rec[12]` (probably the offset's high byte, spec §7)
  raises on read, and an offset write clears it. Offsets are written up to 12.75 MHz until
  the high byte is confirmed.
- `tx_hz` on a channel whose shift code is undecoded raises rather than assuming a
  direction. The range of an undecoded band (codes 4–7) is unknown, so it is not
  checked; a decoded band (0–3) is always range-checked, however it was written.

### Raw buffer and typed views

An image is one mutable `bytearray`; every decoded object is a view that decodes on read
and patches only its own bits on write. Round-trip identity is therefore structural:
bytes nobody touched cannot change, which makes the editor safe while much of the format
is still undecoded. `Channel` uses `__slots__` so assigning a misspelled or edge-only
name (such as `rx_mhz`) raises instead of creating a silent attribute.

### Integer Hz inside, exact decimals at the edges

The engine and `ChannelRecord` hold frequencies and offsets as `int` Hz. Every external
form — CSV text, the `set` field names, MCP results, RepeaterSpec — stays in MHz/kHz and
is converted by `units` with exact decimal arithmetic on the digit tuple, never float.
`"146.65"`, `"146.6500"` and `" 146.65 "` all give 146 650 000 Hz; a sub-Hz value is
refused. User-facing field names stay `rx_mhz`, `tx_mhz` and `offset_khz` because that is
how operators think about them.

### ChannelRecord and validate-then-write

Adapters never write into the byte view field by field. They build a `ChannelRecord`, and
`write_record` runs every setter against a scratch copy of the record (plus its name tag
and name-present word); the real buffer changes only if all succeed. In a record, `None`
for an optional field means "not carried": the target's bits are kept. Equal-value
assignments are no-ops (unchanged band and rx are not re-validated, an unchanged name
keeps its tag bytes, an unchanged user CTCSS is accepted), so a blank or odd record
round-trips through CSV unchanged. `import_csv` and `apply_specs` build every record
before writing any, and save only if every write succeeds, so a bad row leaves no output
file.

### Band and frequency change together

The band code and the rx frequency constrain each other, so `Channel.retune(band, rx_hz)`
validates both before writing either. The `band` setter alone refuses a band that the
channel's current frequency does not fit. Adapters always set band and frequency
together. A `RawCode` 0–3 arriving from text or CSV is normalised to its `Band` so it
cannot bypass the range check.

### Safe writes

- No command writes over any of its inputs unless `--in-place` (MCP `in_place=True`) is
  given, and `--in-place` may overwrite only the command's primary input of the same kind
  (FILE for `set`, BASE for `import-csv`, `apply-specs` and `merge`). It never applies to
  `export-csv` or `extract`, whose output is a different file type, and never to a
  secondary input (the CSV, the specs file, a partial given to `merge`).
- Aliases of an input are detected: different spellings, symlinks (`realpath`) and hard
  links (`samefile`).
- `set` takes an output path or in-place, never both (CLI: a mutually exclusive group;
  MCP and `ops.set_field`: `ValueError`), so a request cannot silently ignore one of them.
- `atomic_write` writes a same-directory temp file (created `O_EXCL`), sets the existing
  target's mode before any data is written, fsyncs, then `os.replace`s. It resolves
  symlinks first, so the link survives and its target is updated. A new file gets the
  umask default; an existing file never gets looser permissions. On any failure the temp
  file is removed and the target is untouched.

### Partial backups by composition

`CloneImage` owns an ALL-sized buffer and exposes `.memory` (`MemoryImage`) and `.setup`
(`SetupImage`), views sharing that buffer: an edit through `clone.memory.channels[1]` is
an edit to the clone. There are no shortcut properties (`clone.channels`), so every call
site states which part of the radio it touches. A partial file loaded on its own is
expanded into a private ALL-sized buffer, so every `layout` offset is the same for all
kinds, and `to_bytes()` returns the kind's own file format and size. Extracting a
partial is just `save_image(clone.memory, out)`.

What each view exposes and how merge treats the shared block `0x180`–`0x1FF` follow the
**measured restore behaviour** (spec §2b), not the file contents alone: a view exposes a
record only if its file carries the whole record and a restore of that file applies it.
SETUP owns VFO B slots 3–4; MEMORY owns Home A and Home B slot 0. `merge` copies only
each given partial's owned ranges, whether one or both partials are given, and compares
the header block instead of copying it (a mismatch is an error, not a choice).

`merge` always needs an ALL base: MEMORY and SETUP backups do not carry the ALL-only
regions, and the tools never invent bytes for a region no input supplies.

The kind is detected by file size (ALL `0x18000`, MEMORY `0xA200`, SETUP `0x400`) because
the header is identical in all three. Any other size, including the radio's 720-byte
`$index.dat`, is refused with the three accepted sizes in the message. A command that
needs something the loaded kind lacks raises `NotInBackup` (a `ValueError`), e.g.
`SETUP backup has no memory channels`.

`Kind` is a `StrEnum` so f-strings, `str()` and JSON render the bare value (`MEMORY`).

### Interop policies

- **Native CSV** column names and order are a contract and do not change. Same-base import
  is byte-identical; on a different base every decoded field is reproduced and undecoded
  bits come from the target, except that a stored name over 8 characters is refused on
  another base and the import stops with no output. A CSV without `ShowName` keeps the target's display mode.
- **CHIRP import** derives band from frequency and Narrow from `Mode == NFM`. The fields
  CHIRP lacks (Tx power HIGH, M-GRP off, clock shift off, user CTCSS 1500 Hz) get these
  defaults only on an empty target channel; an occupied channel keeps its own values.
  Only normal DCS polarity is accepted.
- **RepeaterSpec** rows that the FTM-150 cannot encode (any mode other than FM, digital
  or not; no supported band,
  tx outside rx's band, off-grid frequencies, non-standard tones, inverted DCS, two
  different DCS codes, malformed fields) are skipped with a reason and take no channel;
  they never fail the batch, so one unsupported repeater does not block the rest and the
  agent sees what did not fit and why. Band is the first `BAND_RANGES` match for rx. An offset that
  is not a multiple of 50 kHz or exceeds 12.75 MHz becomes a split channel. Narrow comes
  from `params.bandwidth_khz` (≤ 12.5 kHz is narrow; absent or unparseable stays wide).
  The name is sanitised to ASCII and cut to 8 characters with a note, because a good
  repeater is worth an imperfect label. Written channels get HIGH power, 5 kHz step, skip,
  M-GRP and clock shift off, the name displayed, and the target's own user CTCSS. An
  occupied channel is overwritten with a note. Channels are filled consecutively from
  `start` (default: the first empty channel).

### Engine lists fields, the edge parses text

`engine.record.FIELDS` says which fields are settable; `coerce.PARSERS` says how their
text is parsed and is keyed by exactly those names (a test asserts it). Setters own
validation and list the valid choices in their errors; parsers only turn text into types.

### Runtime and tooling

- Stdlib-only at runtime. `mcp` is an optional extra; `pytest`, `jsonschema`, `ruff` and
  `mypy` are dev extras. Python ≥ 3.13.
- `mypy --strict` and ruff (including `ANN`) are clean and configured in `pyproject.toml`.

## 4. Lessons learned

- **Decode by differential analysis of single-variable captures.** A capture with many
  changes locates the bytes quickly, but cannot pair enum values to bytes; isolate one
  setting per capture for those.
- **Measure hardware behaviour; don't infer it from file contents.** Which records a
  partial restore applies was only knowable by restoring files on the radio. Give each
  file distinct per-record markers so one restore cycle disambiguates every record.
- **A consumer can depend on a field the radio ignores.** ADMS-17 shows names as boxes
  unless the name-present word is set; the name setter keeps it in step with the tag.
- **The radio rebuilds `$index.dat` from the directory**, so tools never write it.
- **A wider reading of the firmware can expose a bit that captures never isolated.** The
  ADMS-17 experiments only used 5 kHz-grid frequencies, so the high nibble of `rec[2]` was
  taken as a single +5 kHz flag. The firmware's fraction-code table, checked against the
  standard 12.5 kHz UHF CB channels already in the captures, showed codes 4 and C as well.
  When a field is decoded, look for anchor values in the captures that exercise the rest of
  its bits.
- **Getter and setter ranges must match**, or an exported value fails to re-import. Where
  a stored value lies outside the settable range, an equal-value write is a no-op.
- **Blank records hold values that do not validate.** Equal-value no-ops keep them
  round-tripping; enabling a record always validates it.
- **A text edge that turns digits into raw codes can bypass validation.** Normalise
  decoded codes to their enum (`as_band`) before writing.
- **Parsing untrusted numeric text needs size and exponent caps.** `Decimal("0e999999999")`
  is cheap to parse but `10**n` on it is not; `units` caps text length, exponent and
  magnitude before scaling.
- **Atomic writes must not loosen permissions or replace symlinks.** Set the mode before
  writing data, and resolve the path so the link is written through.
- **Tests for typed field dicts must check keys in both directions** — missing as well as
  extra — or a dropped key goes unnoticed.
- **MCP tools need full type annotations.** FastMCP derives each tool's schema from them;
  without them every argument is advertised as `string`.

## 5. Testing and verification

Gate (all must be clean):

    venv/bin/ruff check && venv/bin/mypy ftm150 && venv/bin/pytest -q

Fixture conventions:

- `tests/fixtures/radio/` holds radio-made backups of a fictional configuration: `ALL_A`,
  and `ALL_B`, `MEMORY_B`, `SETUP_B` taken from one state. They are read-only ground
  truth. Tests read them and write only to `tmp_path`.
- Bugs are pinned on synthetic images (the `blank` fixture is an all-zero ALL image), not
  on new captures.
- `tests/fixtures/` holds the radio backups above and the upstream RepeaterSpec schema copy.
- Generated artefacts (experiment outputs) go in `generated/` and are
  never committed.

## 6. Follow-ups

- **Expose the firmware-decoded EEPROM fields**, read-only first: the settings and state bytes
  in spec §8c (volume, squelch, voice and Bluetooth settings, menu state) in `dump` / `info`,
  and only later in `set`, each once a capture confirms it.
- **Optional `info` note about `$index.dat`** for ALL images: the radio rebuilds the index only
  at power-up, card insertion or SD FORMAT, so it is stale right after a backup (spec §3). Left
  out for now as likely noise; add it if users misread the index.
- **Guarded invariant:** no edit path writes `0x0400`–`0x047F` of an ALL image, which no
  restore writes back (spec §2d). `tests/test_identity_block_untouched.py` pins it; a new
  write path must keep it.
