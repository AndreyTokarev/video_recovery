#!/usr/bin/env python3
"""Fix video files with container/layout issues for broader player compatibility.

Default mode is lossless remux (stream copy) into a progressive interleaved MP4
with moov at the front (faststart). Optional re-encode fallback for stubborn files.

Requires ffmpeg/ffprobe on PATH.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from analyze_video import analyze


def require_ffmpeg() -> None:
    missing = [name for name in ("ffprobe", "ffmpeg") if shutil.which(name) is None]
    if missing:
        raise SystemExit(
            f"Missing required tools on PATH: {', '.join(missing)}. "
            "Install FFmpeg and retry."
        )


def default_output(src: Path, suffix: str = "_fixed") -> Path:
    return src.with_name(f"{src.stem}{suffix}{src.suffix}")


def run_ffmpeg(cmd: list[str], *, dry_run: bool = False) -> None:
    print("Command:", " ".join(cmd))
    if dry_run:
        return
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed with exit code {result.returncode}")


def remux_progressive(src: Path, dst: Path, *, dry_run: bool = False) -> None:
    """Lossless remux: fMP4 / non-interleaved → progressive MP4 + faststart."""
    cmd = [
        "ffmpeg",
        "-y",
        "-fflags",
        "+genpts",
        "-i",
        str(src),
        "-map",
        "0",
        "-c",
        "copy",
        "-map_metadata",
        "-1",
        "-movflags",
        "+faststart",
        "-avoid_negative_ts",
        "make_zero",
        str(dst),
    ]
    run_ffmpeg(cmd, dry_run=dry_run)


def remux_mkv(src: Path, dst: Path, *, dry_run: bool = False) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-fflags",
        "+genpts",
        "-i",
        str(src),
        "-map",
        "0",
        "-c",
        "copy",
        str(dst),
    ]
    run_ffmpeg(cmd, dry_run=dry_run)


def reencode_compatible(src: Path, dst: Path, *, dry_run: bool = False) -> None:
    """Compatibility re-encode: H.264 yuv420p + AAC LC."""
    cmd = [
        "ffmpeg",
        "-y",
        "-fflags",
        "+genpts",
        "-i",
        str(src),
        "-map",
        "0:v:0?",
        "-map",
        "0:a:0?",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        "-avoid_negative_ts",
        "make_zero",
        str(dst),
    ]
    run_ffmpeg(cmd, dry_run=dry_run)


def verify(dst: Path) -> dict:
    report = analyze(dst, decode_scan=False)
    remaining = [
        f
        for f in report.findings
        if f.severity in ("critical", "high")
    ]
    return {
        "path": report.path,
        "summary": report.summary,
        "remaining_high_or_critical": [f.code for f in remaining],
        "findings": [
            {"severity": f.severity, "code": f.code, "title": f.title}
            for f in report.findings
        ],
    }


def recommend_mode(src: Path) -> str:
    report = analyze(src, decode_scan=False)
    codes = {f.code for f in report.findings}
    if "DECODE_ERRORS" in codes:
        return "reencode"
    if codes & {
        "NON_INTERLEAVED_FRAGMENTS",
        "FRAGMENTED_MP4",
        "MOOV_AT_END",
        "HLS_REMUX_ENCODER",
        "NONZERO_START",
        "AV_START_SKEW",
    }:
        return "remux"
    if codes & {"HEVC", "UNUSUAL_PIX_FMT", "UNUSUAL_AUDIO"}:
        return "reencode"
    return "remux"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Repair video containers for VLC/cross-player compatibility. "
            "Default: lossless remux to progressive interleaved MP4."
        )
    )
    parser.add_argument("input", type=Path, help="Broken / poorly compatible video")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output path (default: <name>_fixed.mp4)",
    )
    parser.add_argument(
        "--mode",
        choices=("auto", "remux", "reencode", "mkv"),
        default="auto",
        help="auto=choose from analysis; remux=stream copy; reencode=H.264/AAC; mkv=copy to Matroska",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Replace the original file after a successful fix (keeps .bak)",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip post-fix analysis",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned ffmpeg command only",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON result",
    )
    args = parser.parse_args(argv)

    require_ffmpeg()
    src = args.input
    if not src.is_file():
        print(f"Error: file not found: {src}", file=sys.stderr)
        return 1

    mode = args.mode
    if mode == "auto":
        mode = recommend_mode(src)
        print(f"Auto-selected mode: {mode}")

    if args.output:
        dst = args.output
    elif mode == "mkv":
        dst = src.with_suffix(".mkv")
    else:
        dst = default_output(src)

    if dst.resolve() == src.resolve() and not args.in_place:
        print(
            "Error: output path equals input; use --in-place or a different -o",
            file=sys.stderr,
        )
        return 1

    # Work to a temp sibling when replacing in place
    work_dst = dst
    if args.in_place:
        work_dst = src.with_name(f"{src.stem}.__fixing__{src.suffix if mode != 'mkv' else '.mkv'}")

    try:
        if mode == "remux":
            remux_progressive(src, work_dst, dry_run=args.dry_run)
        elif mode == "mkv":
            remux_mkv(src, work_dst, dry_run=args.dry_run)
        elif mode == "reencode":
            reencode_compatible(src, work_dst, dry_run=args.dry_run)
        else:
            raise SystemExit(f"Unknown mode: {mode}")
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        if work_dst.exists() and work_dst != dst:
            work_dst.unlink(missing_ok=True)
        return 1

    if args.dry_run:
        return 0

    verification = None
    if not args.no_verify:
        print("\nVerifying output...")
        verification = verify(work_dst)
        print(f"Verify summary: {verification['summary']}")
        if verification["remaining_high_or_critical"]:
            print(
                "Warning: remaining high/critical codes:",
                ", ".join(verification["remaining_high_or_critical"]),
            )

    if args.in_place:
        bak = src.with_suffix(src.suffix + ".bak")
        if bak.exists():
            bak.unlink()
        src.rename(bak)
        final_name = src if mode != "mkv" else src.with_suffix(".mkv")
        work_dst.rename(final_name)
        print(f"Replaced original. Backup: {bak}")
        final_path = final_name
    else:
        if work_dst != dst:
            work_dst.replace(dst)
        final_path = dst

    result = {
        "input": str(src.resolve()),
        "output": str(final_path.resolve()),
        "mode": mode,
        "verification": verification,
    }
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"\nWrote: {final_path}")
        print("Try opening the output in VLC.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
