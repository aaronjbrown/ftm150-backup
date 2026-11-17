# AGENTS.md

Instructions for coding agents working in this repository, whatever tool runs them.
Humans: see [`README.md`](README.md) and [`docs/DESIGN.md`](docs/DESIGN.md).

## What this is

`ftm150` is a Python 3.13 package (library, `ftm150` CLI, optional `ftm150-mcp` server) that
reads and edits the Yaesu FTM-150R/E SD-card backups: ALL (`CLNFTM150nn.dat`, `0x18000` B),
MEMORY (`MEMFTM150nn.dat`, `0xA200` B) and SETUP (`SYSFTM150nn.dat`, `0x400` B). The format
reference is [`docs/FTM-150-clone-format-spec.md`](docs/FTM-150-clone-format-spec.md); its
firmware evidence is [`docs/firmware-evidence.md`](docs/firmware-evidence.md).

## Layer map (DESIGN §2)

```
cli.py   mcp/server.py         thin adapters: parse arguments, call one ops function, format
            │
          ops.py               the single core: load -> validate all -> apply -> save
     ┌──────┼───────────────┐
 coerce.py  interop/        fileio.py      text parsing | format adapters | safe output
     └──────┼───────────────┘
          units.py             exact decimal MHz/kHz <-> int Hz at every edge
            │
          engine/              the binary format and the domain model (bytes in, bytes out)
```

- `engine/` imports only `units` from outside itself and opens no files; `tests/test_layers.py`
  enforces the imports.
- Every CLI/MCP command is one function in `ops.py`; the MCP server never imports the CLI.
- `fileio.py` (atomic writes, the "don't clobber an input" rule) is imported only by `ops`.

## Commands

Set up once: `python3 -m venv venv && venv/bin/pip install -e ".[dev,mcp]"`. The gate, all
of which must be clean before a commit:

    venv/bin/ruff check
    venv/bin/mypy ftm150
    venv/bin/pytest -q

## Rules

1. **Fixtures are fictional.** `tests/fixtures/radio/` holds radio-made backups of a fictional
   configuration and is read-only. Never add a real backup, or values taken from one
   (callsigns, frequencies, settings), to the repository. Pin bugs on synthetic images (the
   `blank` fixture); write experiment output to `generated/` (git-ignored).
2. **Never guess a field.** Every spec change carries a confidence tag (`CONFIRMED`, `LIKELY`,
   `LIKELY (firmware)`, `PARTIAL`, `HYPOTHESIS`, `UNKNOWN`) and its evidence: a controlled
   ADMS-17 capture, a manual citation, or firmware addresses in `docs/firmware-evidence.md`.
   A firmware-only fact is `LIKELY (firmware)`, never `CONFIRMED`, until a radio test proves it.
   The engine decodes only what the spec decodes; undecoded bits are preserved verbatim.
3. **`0x0400`–`0x047F` of an ALL image is never written.** It is the radio's identity and RF
   alignment block; no restore writes it back, so an edit there would silently do nothing.
   `tests/test_identity_block_untouched.py` guards every edit path.
4. **Never overwrite an input.** Write to a new output path; `--in-place` / `in_place=True` only
   when the user asks for it.
5. **Never write `$index.dat`.** The radio rebuilds it from the directory.

## MCP server instructions

`ftm150/mcp/server.py` sends `INSTRUCTIONS` to every MCP client at connect time: the rules for
using the tools on a user's backups. Keep them in step with `ops` and the CLI when behaviour
changes. `tests/test_mcp_server.py` checks that the settable-field list matches
`ftm150.coerce.SETTABLE`.
