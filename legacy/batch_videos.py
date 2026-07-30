#!/usr/bin/env python3
"""Batch helper: analyze and/or fix many videos in a folder."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from analyze_video import analyze, print_human
from fix_video import recommend_mode, remux_progressive, reencode_compatible, verify


VIDEO_EXTS = {".mp4", ".m4v", ".mov", ".mkv", ".webm", ".ts", ".m2ts", ".avi"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze/fix all videos in a directory")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--fix", action="store_true", help="Also write *_fixed.mp4 files")
    parser.add_argument(
        "--mode",
        choices=("auto", "remux", "reencode"),
        default="auto",
    )
    parser.add_argument("--recursive", action="store_true")
    args = parser.parse_args(argv)

    root = args.directory
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 1

    paths = sorted(
        p
        for p in (root.rglob("*") if args.recursive else root.iterdir())
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS and "_fixed" not in p.stem
    )
    if not paths:
        print("No video files found.")
        return 0

    failed = 0
    for path in paths:
        print("=" * 72)
        try:
            report = analyze(path)
            print_human(report)
            if args.fix:
                mode = args.mode if args.mode != "auto" else recommend_mode(path)
                out = path.with_name(f"{path.stem}_fixed.mp4")
                print(f"\nFixing with mode={mode} -> {out.name}")
                if mode == "reencode":
                    reencode_compatible(path, out)
                else:
                    remux_progressive(path, out)
                v = verify(out)
                print(f"Verify: {v['summary']}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAILED {path}: {exc}", file=sys.stderr)

    print("=" * 72)
    print(f"Done. files={len(paths)} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
