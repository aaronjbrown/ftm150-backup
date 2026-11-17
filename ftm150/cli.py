# ftm150/cli.py
"""Argparse adapter over ftm150.ops: parse, call one ops function, print."""
import argparse
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict

from . import ops
from .engine.partial import Kind, partial_kinds


def _cmd_info(args: argparse.Namespace) -> int:
    d = ops.info(args.file)
    if args.json:
        print(json.dumps(d))
        return 0
    v = {k: "n/a" if x is None else x for k, x in d.items()}
    print(f"kind: {v['kind']}")
    print(f"magic: {'AH086$ ok' if d['magic_ok'] else 'BAD'}")
    print(f"regular channels: {v['regular_channels']} ({v['used']} used)")
    print(f"PMS pairs: {v['pms_pairs']}   APO: {v['apo']}")
    return 0


def _cmd_dump(args: argparse.Namespace) -> int:
    rows = ops.rows(args.file)
    if args.json:
        print(json.dumps(rows))
        return 0
    for r in rows:
        print(f"CH{r['Location']:3d} {r['Band']:8} {r['Mode']} "
              f"{float(str(r['Frequency'])):9.4f} {r['Duplex']:6} {r['Tone']:5} "
              f"{r['TxPower']:4} '{r['Name']}'")
    return 0


def _cmd_export_csv(args: argparse.Namespace) -> int:
    ops.export_csv(args.file, args.out, chirp=args.chirp)
    return 0


def _cmd_import_csv(args: argparse.Namespace) -> int:
    ops.import_csv(args.base, args.csv, args.out, chirp=args.chirp,
                   in_place=args.in_place)
    return 0


def _cmd_set(args: argparse.Namespace) -> int:
    ops.set_field(args.file, args.ch, args.field, args.value, args.out,
                  in_place=args.in_place)
    return 0


def _cmd_extract(args: argparse.Namespace) -> int:
    ops.extract(args.file, Kind(args.kind.upper()), args.out)
    return 0


def _cmd_merge(args: argparse.Namespace) -> int:
    ops.merge(args.base, args.out, memory=args.memory, setup=args.setup,
              in_place=args.in_place)
    return 0


def _cmd_apply_specs(args: argparse.Namespace) -> int:
    with open(args.specs, encoding="utf-8") as fh:
        specs = json.load(fh)
    result = ops.apply_specs(args.base, specs, args.out, start=args.start,
                             in_place=args.in_place, protect=[args.specs])
    if args.json:
        print(json.dumps(asdict(result), default=str))
        return 0
    for a in result.applied:
        print(f"CH{a.channel:3d} {a.name:16} {a.rx_mhz:9.4f} {a.shift}"
              + ("  " + "; ".join(a.notes) if a.notes else ""))
    for s in result.skipped:
        print(f"SKIP {s.source_id or s.name}: {s.reason}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ftm150")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("info")
    s.add_argument("file")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=_cmd_info)

    s = sub.add_parser("dump")
    s.add_argument("file")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=_cmd_dump)

    s = sub.add_parser("export-csv")
    s.add_argument("file")
    s.add_argument("out")
    s.add_argument("--chirp", action="store_true")
    s.set_defaults(fn=_cmd_export_csv)

    s = sub.add_parser("import-csv")
    s.add_argument("base")
    s.add_argument("csv")
    s.add_argument("out")
    s.add_argument("--chirp", action="store_true", help="CSV is in CHIRP format")
    s.add_argument("--in-place", action="store_true",
                   help="allow OUT to be BASE (atomic overwrite)")
    s.set_defaults(fn=_cmd_import_csv)

    s = sub.add_parser("apply-specs")
    s.add_argument("base")
    s.add_argument("specs")
    s.add_argument("out")
    s.add_argument("--start", type=int, default=None)
    s.add_argument("--json", action="store_true")
    s.add_argument("--in-place", action="store_true",
                   help="allow OUT to be BASE (atomic overwrite)")
    s.set_defaults(fn=_cmd_apply_specs)

    s = sub.add_parser("set")
    s.add_argument("file")
    s.add_argument("ch", type=int)
    s.add_argument("field")
    s.add_argument("value")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--out", help="output path (must differ from FILE)")
    g.add_argument("--in-place", action="store_true", help="atomically overwrite FILE")
    s.set_defaults(fn=_cmd_set)

    s = sub.add_parser("extract", help="write the MEMORY or SETUP backup an ALL image carries")
    s.add_argument("file", help="ALL backup (CLNFTM150nn.dat)")
    s.add_argument("kind", type=str.lower, choices=[k.lower() for k in partial_kinds()])
    s.add_argument("out", help="output path (must differ from FILE)")
    s.set_defaults(fn=_cmd_extract)

    merge_p = sub.add_parser(
        "merge", help="overlay MEMORY and/or SETUP backups onto an ALL image (spec 2b)")
    merge_p.add_argument("base", help="ALL backup (CLNFTM150nn.dat)")
    merge_p.add_argument("out")
    merge_p.add_argument("--memory", help="MEMORY backup (MEMFTM150nn.dat)")
    merge_p.add_argument("--setup", help="SETUP backup (SYSFTM150nn.dat)")
    merge_p.add_argument("--in-place", action="store_true",
                         help="allow OUT to be BASE (atomic overwrite)")
    merge_p.set_defaults(fn=_cmd_merge)

    args = p.parse_args(argv)
    if args.cmd == "merge" and args.memory is None and args.setup is None:
        merge_p.error("at least one of --memory/--setup is required")
    fn: Callable[[argparse.Namespace], int] = args.fn
    try:
        return fn(args)
    except (ValueError, KeyError, OSError, IndexError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
