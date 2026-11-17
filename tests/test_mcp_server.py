import asyncio
import os
import re
import shutil
import subprocess
import sys

import pytest

from ftm150 import CloneImage, ops
from ftm150.mcp import server
from tests.files import ALL_A, ALL_B, MEMORY_B, SETUP_B, load


def read(path):
    with open(path, "rb") as fh:
        return fh.read()

SPEC = {"name": "N0CALL", "callsign": "N0CALL", "rx_frequency_mhz": "146.700",
        "tx_frequency_mhz": "146.100", "mode": "FM", "ctcss_tx_hz": "91.5",
        "ctcss_rx_hz": None, "dcs_code": None, "source_id": "XX:42"}


def test_tools_registered():
    # list_tools() is a coroutine; asyncio.run keeps the test dependency-free.
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert names == {"apply_repeater_specs", "set_channel_field",
                     "dump_channels", "image_info", "import_channels_csv",
                     "extract_backup", "merge_backups"}


def test_server_does_not_import_cli():
    code = "import ftm150.mcp.server, sys; assert 'ftm150.cli' not in sys.modules"
    # -P: don't put the CWD on sys.path
    r = subprocess.run([sys.executable, "-P", "-c", code], capture_output=True, text=True,
                       cwd=os.path.dirname(os.path.dirname(__file__)))
    assert r.returncode == 0, r.stderr


def test_set_channel_field_in_place(tmp_path):
    f = str(tmp_path / "f.dat")
    shutil.copy(ALL_A, f)
    server.set_channel_field(f, 1, "rx_mhz", "146.6", in_place=True)
    assert load(CloneImage, f).memory.channels[1].rx_hz == 146_600_000
    with pytest.raises(ValueError):
        server.set_channel_field(f, 1, "rx_mhz", "146.6")   # no out, no in_place


def test_set_channel_field_refuses_out_path_with_in_place(tmp_path):
    f = str(tmp_path / "f.dat")
    shutil.copy(ALL_A, f)
    out = tmp_path / "o.dat"
    with pytest.raises(ValueError, match="not both"):
        server.set_channel_field(f, 1, "rx_mhz", "146.6", str(out), in_place=True)
    assert not out.exists()
    assert read(f) == read(ALL_A)


def test_import_channels_csv(tmp_path):
    c = str(tmp_path / "c.csv")
    ops.export_csv(ALL_A, c)
    out = str(tmp_path / "o.dat")
    res = server.import_channels_csv(ALL_A, c, out)
    assert res["out_path"] == out and res["imported"] > 0
    assert load(CloneImage, out).to_bytes() == load(CloneImage, ALL_A).to_bytes()
    with pytest.raises(ValueError):
        server.import_channels_csv(ALL_A, c, ALL_A)


def test_tool_schema_types():
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    props = tools["set_channel_field"].inputSchema["properties"]
    assert props["channel"]["type"] == "integer"
    assert tools["apply_repeater_specs"].inputSchema["properties"]["specs"]["type"] == "array"


def test_apply_refuses_overwriting_base(tmp_path):
    with pytest.raises(ValueError):
        server.apply_repeater_specs(ALL_A, [SPEC], ALL_A)


def test_set_channel_field_refuses_overwriting_base():
    with pytest.raises(ValueError):
        server.set_channel_field(ALL_A, 1, "ctcss_hz", "88.5", ALL_A)


def test_apply_writes_out(tmp_path):
    out = str(tmp_path / "out.dat")
    result = server.apply_repeater_specs(ALL_A, [SPEC], out, start_channel=200)
    assert len(result["applied"]) == 1
    assert os.path.exists(out)


def test_image_info(tmp_path):
    info = server.image_info(ALL_A)
    assert info["magic_ok"] is True
    assert info["regular_channels"] == 999


def test_set_channel_field_mhz_alias_reports_user_units(tmp_path):
    out = str(tmp_path / "out.dat")
    result = server.set_channel_field(ALL_A, 1, "rx_mhz", "146.6000", out)
    assert result == {"channel": 1, "field": "rx_mhz", "value": "146.6", "out_path": out}
    assert load(CloneImage, out).memory.channels[1].rx_hz == 146_600_000


def test_image_info_reports_kind():
    assert server.image_info(SETUP_B)["kind"] == "SETUP"
    assert server.image_info(MEMORY_B)["apo"] is None


def test_extract_and_merge_tools(tmp_path):
    out = tmp_path / "s.dat"
    assert server.extract_backup(ALL_B, "setup", str(out)) == {"out_path": str(out)}
    assert out.read_bytes() == read(SETUP_B)
    merged = tmp_path / "c.dat"
    assert server.merge_backups(ALL_A, str(merged), setup_path=str(out)) == {
        "out_path": str(merged)}
    assert load(CloneImage, str(merged)).setup.to_bytes()[:0x180] == read(SETUP_B)[:0x180]


def _copy(src, dst):
    dst.write_bytes(read(src))
    return str(dst)


def test_dump_channels_output_schema_and_structured_result():
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    schema = tools["dump_channels"].outputSchema
    assert schema["required"] == ["result"]
    assert schema["properties"]["result"]["type"] == "array"
    assert schema["properties"]["result"]["items"]["type"] == "object"
    got = asyncio.run(server.mcp.call_tool("dump_channels", {"path": ALL_B}))
    structured = got[1] if isinstance(got, tuple) else got
    assert structured == {"result": ops.rows(ALL_B)}


def test_apply_repeater_specs_out_and_in_place_rules(tmp_path):
    base = _copy(ALL_A, tmp_path / "b.dat")
    before = read(base)
    with pytest.raises(ValueError, match="output path is required"):
        server.apply_repeater_specs(base, [SPEC], start_channel=200)
    assert read(base) == before
    out = str(tmp_path / "o.dat")
    res = server.apply_repeater_specs(base, [SPEC], out, start_channel=200, in_place=True)
    assert res["out_path"] == out and os.path.exists(out) and read(base) == before
    res = server.apply_repeater_specs(base, [SPEC], start_channel=200, in_place=True)
    assert res["out_path"] == base and read(base) == read(out) != before


def test_import_channels_csv_in_place_rules(tmp_path):
    base = _copy(ALL_A, tmp_path / "b.dat")
    c = str(tmp_path / "c.csv")
    ops.export_csv(ALL_A, c, chirp=True)
    csv_before = read(c)
    with pytest.raises(ValueError, match="differ from every input"):
        server.import_channels_csv(base, c, c, chirp=True, in_place=True)
    assert read(c) == csv_before
    res = server.import_channels_csv(base, c, chirp=True, in_place=True)
    assert res["out_path"] == base and res["imported"] > 0


def test_merge_backups_never_writes_over_a_partial(tmp_path):
    base = _copy(ALL_A, tmp_path / "b.dat")
    mem = _copy(MEMORY_B, tmp_path / "m.dat")
    with pytest.raises(ValueError, match="differ from every input"):
        server.merge_backups(base, mem, memory_path=mem, in_place=True)
    assert read(mem) == read(MEMORY_B) and read(base) == read(ALL_A)


def test_tool_argument_schema_types():
    tools = {t.name: t.inputSchema["properties"] for t in asyncio.run(server.mcp.list_tools())}
    opt_str = {"anyOf": [{"type": "string"}, {"type": "null"}]}

    def types(name):
        return {k: v.get("type") or {"anyOf": v["anyOf"]} for k, v in tools[name].items()}

    assert types("import_channels_csv") == {
        "base_path": "string", "csv_path": "string", "out_path": opt_str,
        "chirp": "boolean", "in_place": "boolean"}
    assert types("extract_backup") == {"path": "string", "kind": "string", "out_path": "string"}
    assert types("merge_backups") == {
        "base_path": "string", "out_path": opt_str, "memory_path": opt_str,
        "setup_path": opt_str, "in_place": "boolean"}


def test_server_publishes_instructions():
    text = server.mcp.instructions
    assert text == server.INSTRUCTIONS
    for rule in ("out_path", "in_place=True", "dump_channels", "0x0400-0x047F", "$index.dat"):
        assert rule in text, rule


def test_instructions_list_exactly_the_settable_fields():
    from ftm150.coerce import SETTABLE
    line = next(ln for ln in server.INSTRUCTIONS.split("\n- ")
                if ln.startswith("set_channel_field fields:"))
    fields = re.sub(r"\([^)]*\)", "", line.split(":", 1)[1])
    listed = {f.strip(" .\n") for f in fields.split(",")}
    assert listed == set(SETTABLE)
