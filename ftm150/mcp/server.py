"""FastMCP server exposing ftm150 read/edit tools to agents.

Thin adapter over `ftm150.ops`; all validation and safe-write rules live there.
"""
from dataclasses import asdict

from mcp.server.fastmcp import FastMCP

from .. import ops

INSTRUCTIONS = """\
Read and edit Yaesu FTM-150R/E SD-card backups: ALL images (CLNFTM150nn.dat, 0x18000 bytes), \
MEMORY backups (MEMFTM150nn.dat, 0xA200 bytes) and SETUP backups (SYSFTM150nn.dat, 0x400 bytes). \
The kind is detected from the file size; image_info reports it.

Rules:
- Never overwrite the user's files. Always pass a new out_path; use in_place=True only when the \
user explicitly asks for it.
- Verify every edit: read the output with dump_channels (or image_info) and check that the \
intended fields, and only those, changed.
- Values the radio cannot represent are refused with an error; report the error to the user \
rather than guessing another value.
- SETUP backups carry no memory channels; channel tools work on ALL and MEMORY backups.
- To move a channel to another band, change band and frequency together (import_channels_csv or \
apply_repeater_specs); set_channel_field refuses a band whose range excludes the current frequency.
- set_channel_field fields: name (ASCII, at most 8 characters), band, rx_mhz, tx_mhz (split \
channels only), offset_khz, mode, narrow, shift, tone_mode, ctcss_hz, dcs, step_khz, power, skip, \
mgrp, clock_shift, user_ctcss_hz, enabled, show_name.
- The tools never write the radio's identity and RF-alignment bytes (0x0400-0x047F), and never \
write $index.dat. To load a result, copy it to the card's FTM150/BACKUP folder under a \
CLNFTM150nn.dat / MEMFTM150nn.dat / SYSFTM150nn.dat name; the radio indexes it at the next \
power-up or card insertion.
"""

mcp = FastMCP("ftm150", instructions=INSTRUCTIONS)


@mcp.tool()
def apply_repeater_specs(base_path: str, specs: list[dict[str, object]],
                         out_path: str | None = None, start_channel: int | None = None,
                         in_place: bool = False) -> dict[str, object]:
    """Write RepeaterSpec rows onto base_path; return applied/skipped.

    Give out_path (preferred) or set in_place=True; out_path may not equal base_path.
    """
    return asdict(ops.apply_specs(base_path, specs, out_path, start=start_channel,
                                  in_place=in_place))


@mcp.tool()
def set_channel_field(base_path: str, channel: int, field: str, value: str,
                      out_path: str | None = None,
                      in_place: bool = False) -> dict[str, object]:
    """Set one field on one channel; return channel, field, value and out_path.

    Give out_path (preferred) or set in_place=True, not both; out_path may not
    equal base_path.
    """
    return ops.set_field(base_path, channel, field, value, out_path, in_place=in_place)


@mcp.tool()
def import_channels_csv(base_path: str, csv_path: str, out_path: str | None = None,
                        chirp: bool = False, in_place: bool = False) -> dict[str, object]:
    """Apply a native (or CHIRP, chirp=True) CSV onto base_path; return count and out_path."""
    n, out = ops.import_csv(base_path, csv_path, out_path, chirp=chirp, in_place=in_place)
    return {"imported": n, "out_path": out}


@mcp.tool()
def dump_channels(path: str) -> list[dict[str, object]]:
    """Return every enabled channel as a row dict."""
    return ops.rows(path)


@mcp.tool()
def image_info(path: str) -> dict[str, object]:
    """Return kind (ALL/MEMORY/SETUP), magic, counts and APO for a backup.

    Values the backup kind does not carry are None.
    """
    return ops.info(path)


@mcp.tool()
def extract_backup(path: str, kind: str, out_path: str) -> dict[str, object]:
    """Write the MEMORY or SETUP backup (kind "memory"/"setup") carried by the
    ALL image at path to out_path, which may not equal path."""
    return {"out_path": ops.extract(path, kind, out_path)}


@mcp.tool()
def merge_backups(base_path: str, out_path: str | None = None,
                  memory_path: str | None = None, setup_path: str | None = None,
                  in_place: bool = False) -> dict[str, object]:
    """Overlay a MEMORY and/or SETUP backup onto the ALL image base_path.

    Only each kind's owned ranges are copied (SETUP: settings/VFO; MEMORY:
    channels/PMS/Home); headers must match. Give out_path (preferred) or
    in_place=True; out_path may never equal a partial's path.
    """
    return {"out_path": ops.merge(base_path, out_path, memory=memory_path,
                                  setup=setup_path, in_place=in_place)}


def main() -> int:
    """Run the MCP server over stdio."""
    mcp.run()
    return 0
