"""Command-line entry points."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from video_recovery import __version__
from video_recovery.analyze import analyze, print_human
from video_recovery.batch import process_directory
from video_recovery.fix import fix_file


def _cmd_analyze(args: argparse.Namespace) -> int:
    try:
        report = analyze(args.input, decode_scan=args.decode_scan)
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print_human(report)
    return 0


def _cmd_fix(args: argparse.Namespace) -> int:
    try:
        result = fix_file(
            args.input,
            mode=args.mode,
            output=args.output,
            in_place=args.in_place,
            verify_output=not args.no_verify,
            dry_run=args.dry_run,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if args.dry_run:
        print(f"Would write: {result['output']} (mode={result['mode']})")
        return 0
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Wrote: {result['output']}")
        verification = result.get("verification")
        if verification:
            print(f"Verify: {verification['summary']}")
            remaining = verification.get("remaining_high_or_critical") or []
            if remaining:
                print("Warning: remaining high/critical:", ", ".join(remaining))
    return 0


def _cmd_batch(args: argparse.Namespace) -> int:
    try:
        result = process_directory(
            args.directory,
            fix=args.fix,
            only_if_needed=not args.force_all,
            mode=args.mode,
            recursive=args.recursive,
            in_place=args.in_place,
            verify_output=not args.no_verify,
            log=print,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 1 if result.failed else 0


def _cmd_gui(_args: argparse.Namespace) -> int:
    from video_recovery.gui.app import main as gui_main

    return gui_main()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="video-recovery",
        description=(
            "Diagnose and repair course videos with broken MP4 containers "
            "(HLS remux / non-interleaved fMP4)."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_analyze = sub.add_parser("analyze", help="Analyze a single video")
    p_analyze.add_argument("input", type=Path)
    p_analyze.add_argument("--decode-scan", action="store_true")
    p_analyze.add_argument("--json", action="store_true")
    p_analyze.set_defaults(func=_cmd_analyze)

    p_fix = sub.add_parser("fix", help="Fix a single video")
    p_fix.add_argument("input", type=Path)
    p_fix.add_argument("-o", "--output", type=Path)
    p_fix.add_argument(
        "--mode",
        choices=("auto", "remux", "reencode", "mkv"),
        default="auto",
    )
    p_fix.add_argument("--in-place", action="store_true")
    p_fix.add_argument("--no-verify", action="store_true")
    p_fix.add_argument("--dry-run", action="store_true")
    p_fix.add_argument("--json", action="store_true")
    p_fix.set_defaults(func=_cmd_fix)

    p_batch = sub.add_parser("batch", help="Analyze/fix all videos in a folder")
    p_batch.add_argument("directory", type=Path)
    p_batch.add_argument("--fix", action="store_true", help="Write fixed files")
    p_batch.add_argument(
        "--force-all",
        action="store_true",
        help="Fix every file even without high/critical findings",
    )
    p_batch.add_argument(
        "--mode",
        choices=("auto", "remux", "reencode", "mkv"),
        default="auto",
    )
    p_batch.add_argument("--recursive", action="store_true", default=True)
    p_batch.add_argument("--no-recursive", action="store_false", dest="recursive")
    p_batch.add_argument("--in-place", action="store_true")
    p_batch.add_argument("--no-verify", action="store_true")
    p_batch.set_defaults(func=_cmd_batch)

    p_gui = sub.add_parser("gui", help="Open the graphical interface")
    p_gui.set_defaults(func=_cmd_gui)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
