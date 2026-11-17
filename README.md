# FTM-150 clone format and editor

A documented file format and a tested editor for the SD-card backups of the Yaesu
**FTM-150R/E**: the full ALL image (`CLNFTM150nn.dat`) and the radio's MEMORY
(`MEMFTM150nn.dat`) and SETUP (`SYSFTM150nn.dat`) partial backups.

- [`docs/FTM-150-clone-format-spec.md`](docs/FTM-150-clone-format-spec.md) — the format
  reference, with a confidence tag and evidence for every field.
- [`docs/firmware-evidence.md`](docs/firmware-evidence.md) — the firmware evidence (code
  addresses and tags) behind the spec's `LIKELY (firmware)` statements, one section per spec
  section.
- [`docs/DESIGN.md`](docs/DESIGN.md) — how the `ftm150` package is built and why.

## Repository layout

- `ftm150/` — the Python package (library, `ftm150` CLI, optional `ftm150-mcp` server).
- `AGENTS.md` — instructions for coding agents (any tool).
- `CHANGELOG.md` — release notes.
- `tests/` — the pytest suite.
- `docs/` — format spec, firmware evidence and design.
- `tests/fixtures/radio/` — backups of a fictional configuration (read-only).
- `generated/` — git-ignored output.

## Install

    python3 -m venv venv
    venv/bin/pip install -e .              # the ftm150 command
    venv/bin/pip install -e ".[mcp]"       # plus the ftm150-mcp server
    venv/bin/pip install -e ".[dev,mcp]"   # plus pytest, jsonschema, ruff, mypy

Python ≥ 3.13. The runtime uses only the standard library; `mcp` is optional.

## CLI

    ftm150 info [--json] FILE
    ftm150 dump [--json] FILE
    ftm150 set FILE CH FIELD VALUE (--out OUT | --in-place)
    ftm150 export-csv FILE OUT [--chirp]
    ftm150 import-csv BASE CSV OUT [--chirp] [--in-place]
    ftm150 apply-specs BASE SPECS.json OUT [--start N] [--json] [--in-place]
    ftm150 extract FILE {memory,setup} OUT
    ftm150 merge BASE OUT [--memory MEM] [--setup SYS] [--in-place]

`venv/bin/python -m ftm150 …` works too.

- `info` — backup kind (first line), magic check, channel counts, PMS pairs, APO; `n/a`
  (JSON `null`) for what that kind does not carry.
- `dump` — every enabled channel; `--json` gives one object per channel (native CSV
  columns, typed values).
- `set` — edit one field of channel `CH` (1–999). Settable fields: `name`, `band`,
  `rx_mhz`, `tx_mhz` (split channels only), `offset_khz`, `mode`, `narrow`, `shift`,
  `tone_mode`, `ctcss_hz`, `dcs`, `step_khz`, `power`, `skip`, `mgrp`, `clock_shift`,
  `user_ctcss_hz`, `enabled`, `show_name`. Invalid values are refused with the valid
  choices.
- `export-csv` — enabled channels as native CSV (lossless) or, with `--chirp`, CHIRP CSV.
- `import-csv` — apply a native (or `--chirp`) CSV onto BASE and write OUT. Same-base
  import is byte-identical; on another base every decoded field is reproduced, except that a stored name over
  8 characters is refused and the import stops with no output. With
  `--chirp`, fields CHIRP lacks (Tx power HIGH, M-GRP off, clock shift off, user CTCSS
  1500 Hz) get those defaults only on empty channels.
- `apply-specs` — write a JSON list of RepeaterSpec rows onto consecutive channels from
  `--start` (default: first empty channel). Rows the radio cannot represent are skipped
  and reported with a reason.
- `extract` — write the MEMORY or SETUP backup an ALL image carries.
- `merge` — overlay a MEMORY and/or SETUP backup onto an ALL image, copying only each
  kind's own records (spec §2b); headers must match. At least one of `--memory`/`--setup`.

The backup kind is detected from the file size. `info`, `dump`, `set`, the CSV commands
and `apply-specs` accept ALL and MEMORY backups; a SETUP backup carries no channels.

Invalid input and I/O failures print `error: <msg>` on stderr, exit 2 and write nothing.
Programming errors are not caught, so they surface with a traceback.

### Writes

- No command overwrites an input unless `--in-place` is given. `--in-place` lets OUT be
  the command's primary input (FILE for `set`, BASE for `import-csv`, `apply-specs`,
  `merge`); it never lets OUT be the CSV, the specs file or a partial given to `merge`.
  `export-csv` and `extract` have no `--in-place`.
- `set` takes `--out` or `--in-place`, not both.
- Writes are atomic (temp file, fsync, rename), keep the existing file's permissions and
  write through symlinks.

## MCP server

`ftm150-mcp` (stdio) exposes the same operations except `export-csv` as typed tools:

| Tool | Arguments |
|---|---|
| `image_info` | `path` |
| `dump_channels` | `path` |
| `set_channel_field` | `base_path, channel, field, value, out_path?, in_place?` |
| `import_channels_csv` | `base_path, csv_path, out_path?, chirp?, in_place?` |
| `apply_repeater_specs` | `base_path, specs, out_path?, start_channel?, in_place?` |
| `extract_backup` | `path, kind, out_path` |
| `merge_backups` | `base_path, out_path?, memory_path?, setup_path?, in_place?` |

Write tools need `out_path`, or `in_place=True` to write over `base_path`.
`set_channel_field` refuses both together. `specs` follows
`ftm150/schemas/repeater_spec.schema.json`.

The server also sends usage instructions to the client when it connects (safe-write and
verification rules, settable fields, how to load a result onto the card), so any MCP client
gets them without extra setup. They are `INSTRUCTIONS` in `ftm150/mcp/server.py`.

## Development

    venv/bin/ruff check && venv/bin/mypy ftm150 && venv/bin/pytest -q

See [`docs/DESIGN.md`](docs/DESIGN.md) §5 for fixture conventions.

## Contribution rules

1. **Never guess a field into `CONFIRMED`** — use a controlled ADMS-17 single-variable
   diff or a manual citation.
2. Keep fixture images read-only; write experiment images and generated output to `generated/`.
3. After every finding, update `docs/FTM-150-clone-format-spec.md` with offset, size,
   encoding, value mapping and a confidence tag. A finding from the firmware is tagged
   `LIKELY (firmware)` and gets its addresses in `docs/firmware-evidence.md`.
4. Treat byte order as unproven until a capture shows it.

## Reference documents

- ADMS-17 Instruction Manual (Yaesu) — SD backup workflow.
- FTM-150R/E Operating and Advance Manuals (Yaesu) — feature and field semantics.

## License

GPL-3.0-or-later. See [`LICENSE`](LICENSE).
