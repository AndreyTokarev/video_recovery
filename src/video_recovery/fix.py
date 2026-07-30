"""Fix video files with container/layout issues for broader player compatibility."""

from __future__ import annotations

import subprocess
from pathlib import Path

from video_recovery.analyze import analyze
from video_recovery.ffmpeg_tools import require_ffmpeg

FixMode = str  # auto | remux | reencode | mkv


def default_output(src: Path, suffix: str = "_fixed") -> Path:
    return src.with_name(f"{src.stem}{suffix}.mp4")


def run_ffmpeg(cmd: list[str], *, dry_run: bool = False) -> None:
    if dry_run:
        return
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed with exit code {result.returncode}")


def remux_progressive(src: Path, dst: Path, *, dry_run: bool = False) -> None:
    """Lossless remux: fMP4 / non-interleaved → progressive MP4 + faststart."""
    ffmpeg, _ = require_ffmpeg()
    cmd = [
        ffmpeg,
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
    ffmpeg, _ = require_ffmpeg()
    cmd = [
        ffmpeg,
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
    ffmpeg, _ = require_ffmpeg()
    cmd = [
        ffmpeg,
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
    remaining = [f for f in report.findings if f.severity in ("critical", "high")]
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


def fix_file(
    src: Path,
    *,
    mode: FixMode = "auto",
    output: Path | None = None,
    in_place: bool = False,
    verify_output: bool = True,
    dry_run: bool = False,
) -> dict:
    require_ffmpeg()
    if not src.is_file():
        raise FileNotFoundError(src)

    resolved_mode = mode if mode != "auto" else recommend_mode(src)

    if output is not None:
        dst = output
    elif resolved_mode == "mkv":
        dst = src.with_suffix(".mkv")
    else:
        dst = default_output(src)

    if dst.resolve() == src.resolve() and not in_place:
        raise ValueError("Output path equals input; use in_place=True or another path")

    work_dst = dst
    if in_place:
        suffix = ".mkv" if resolved_mode == "mkv" else src.suffix
        work_dst = src.with_name(f"{src.stem}.__fixing__{suffix}")

    try:
        if resolved_mode == "remux":
            remux_progressive(src, work_dst, dry_run=dry_run)
        elif resolved_mode == "mkv":
            remux_mkv(src, work_dst, dry_run=dry_run)
        elif resolved_mode == "reencode":
            reencode_compatible(src, work_dst, dry_run=dry_run)
        else:
            raise ValueError(f"Unknown mode: {resolved_mode}")
    except Exception:
        if work_dst.exists() and work_dst != dst:
            work_dst.unlink(missing_ok=True)
        raise

    if dry_run:
        return {
            "input": str(src.resolve()),
            "output": str(dst.resolve()),
            "mode": resolved_mode,
            "dry_run": True,
            "verification": None,
        }

    verification = None
    if verify_output:
        verification = verify(work_dst)

    if in_place:
        bak = src.with_suffix(src.suffix + ".bak")
        if bak.exists():
            bak.unlink()
        src.rename(bak)
        final_name = src if resolved_mode != "mkv" else src.with_suffix(".mkv")
        work_dst.rename(final_name)
        final_path = final_name
    else:
        if work_dst != dst:
            work_dst.replace(dst)
        final_path = dst

    return {
        "input": str(src.resolve()),
        "output": str(final_path.resolve()),
        "mode": resolved_mode,
        "verification": verification,
    }
