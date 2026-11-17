# Changelog

All notable changes to this project. Versions follow [semantic versioning](https://semver.org/); the version is set in `pyproject.toml`.

## 1.0.0 — 2026-11-17

First public release.

- **Format specification** (`docs/FTM-150-clone-format-spec.md`) for the FTM-150R/E SD-card backups: the ALL image (`CLNFTM150nn.dat`), the MEMORY (`MEMFTM150nn.dat`) and SETUP (`SYSFTM150nn.dat`) partial backups, `$index.dat` and the ADMS-17 `.FTM150` file. Every field carries a confidence tag and its evidence: tested on a radio, or derived from the firmware.
- **Firmware evidence** (`docs/firmware-evidence.md`): the MAIN/SUB code addresses behind every firmware-derived statement, one section per spec section.
- **`ftm150` Python package** (Python ≥ 3.13, standard library only): read, validate and edit backups byte-exactly. Undecoded bits and regions are carried through unchanged, and values the radio cannot represent are refused.
- **`ftm150` CLI**: `info`, `dump`, `set`, `export-csv` / `import-csv` (native or CHIRP CSV), `apply-specs` (write RepeaterSpec rows onto channels), `extract` and `merge` (MEMORY/SETUP partial backups). Writes are atomic and never overwrite an input without `--in-place`.
- **`ftm150-mcp`**: an optional MCP server exposing the same operations to AI agents (install with the `mcp` extra; see the README). It sends its usage rules (safe writes, verification, settable fields, loading a result onto the card) to the client as server instructions.
- Edits never change the per-radio identity and RF-alignment bytes `0x0400`–`0x047F`, which a restore never writes; a test suite guards this for every write path.
