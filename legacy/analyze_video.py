#!/usr/bin/env python3
"""Analyze video files for container/codec issues that break cross-player playback.

Requires ffprobe/ffmpeg on PATH. Uses stdlib + local mp4_boxes parser.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from mp4_boxes import (
    find_all,
    format_size,
    parse_tfdt,
    parse_tfhd,
    parse_top_level,
    parse_trun,
    read_payload,
)


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


@dataclass
class Finding:
    severity: str
    code: str
    title: str
    detail: str
    fix_hint: str = ""


@dataclass
class AnalysisReport:
    path: str
    file_size: int
    probe: dict = field(default_factory=dict)
    container: dict = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    summary: str = ""

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def sort(self) -> None:
        self.findings.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 99), f.code))


def require_ffmpeg() -> None:
    missing = [name for name in ("ffprobe", "ffmpeg") if shutil.which(name) is None]
    if missing:
        raise SystemExit(
            f"Missing required tools on PATH: {', '.join(missing)}. "
            "Install FFmpeg and retry."
        )


def run_ffprobe(path: Path) -> dict:
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        "-show_chapters",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "ffprobe failed").strip()
        raise RuntimeError(err)
    return json.loads(result.stdout)


def scan_decode_errors(path: Path, timeout_s: int = 120) -> list[str]:
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(path),
        "-f",
        "null",
        "-",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return ["decode scan timed out"]
    lines = [ln.strip() for ln in (result.stderr or "").splitlines() if ln.strip()]
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for line in lines:
        if line not in seen:
            seen.add(line)
            unique.append(line)
    return unique[:40]


def analyze_container(path: Path) -> dict:
    boxes = parse_top_level(path, recurse=True)
    top = [{"type": b.type, "offset": b.offset, "size": b.size} for b in boxes]
    moof_boxes = find_all(boxes, "moof")
    mdat_boxes = [b for b in boxes if b.type == "mdat"]
    moov_boxes = [b for b in boxes if b.type == "moov"]
    mvex = find_all(boxes, "mvex")
    stss = find_all(boxes, "stss")
    elst = find_all(boxes, "elst")

    fragments: list[dict] = []
    for moof in moof_boxes:
        frag: dict = {"offset": moof.offset, "size": moof.size, "tracks": []}
        for traf in [c for c in moof.children if c.type == "traf"]:
            track_info: dict = {}
            for child in traf.children:
                payload = read_payload(path, child)
                if child.type == "tfhd":
                    track_info["tfhd"] = parse_tfhd(payload)
                elif child.type == "trun":
                    track_info["trun"] = parse_trun(payload)
                elif child.type == "tfdt":
                    track_info["tfdt"] = parse_tfdt(payload)
            frag["tracks"].append(track_info)
        fragments.append(frag)

    moov_offset = moov_boxes[0].offset if moov_boxes else None
    first_mdat = mdat_boxes[0].offset if mdat_boxes else None
    moov_after_mdat = (
        moov_offset is not None
        and first_mdat is not None
        and moov_offset > first_mdat
    )

    # Interleaving heuristic: many small interleaved mdats vs few giant mono-track fragments
    sample_counts = []
    track_ids = []
    for frag in fragments:
        for track in frag["tracks"]:
            trun = track.get("trun") or {}
            tfhd = track.get("tfhd") or {}
            if "sample_count" in trun:
                sample_counts.append(trun["sample_count"])
            if "track_id" in tfhd:
                track_ids.append(tfhd["track_id"])

    mono_track_fragments = False
    if len(fragments) >= 2 and all(len(f["tracks"]) == 1 for f in fragments):
        # Distinct track ids across consecutive fragments
        ids = []
        for f in fragments:
            tid = (f["tracks"][0].get("tfhd") or {}).get("track_id")
            if tid is not None:
                ids.append(tid)
        if len(set(ids)) > 1 and len(fragments) <= 8:
            # Few fragments, each owning one track → classic "all audio then all video"
            mono_track_fragments = True

    return {
        "top_level": top,
        "is_fragmented": bool(moof_boxes) or bool(mvex),
        "moof_count": len(moof_boxes),
        "mdat_count": len(mdat_boxes),
        "has_mvex": bool(mvex),
        "moov_after_mdat": moov_after_mdat,
        "moov_offset": moov_offset,
        "has_sync_sample_table": bool(stss),
        "has_edit_list": bool(elst),
        "fragments": fragments,
        "mono_track_fragments": mono_track_fragments,
        "fragment_sample_counts": sample_counts,
        "fragment_track_ids": track_ids,
    }


def build_findings(report: AnalysisReport) -> None:
    probe = report.probe
    container = report.container
    fmt = probe.get("format") or {}
    streams = probe.get("streams") or []
    video = [s for s in streams if s.get("codec_type") == "video"]
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    tags = fmt.get("tags") or {}
    encoder = ""
    for s in streams:
        encoder = (s.get("tags") or {}).get("encoder") or encoder
    encoder = encoder or tags.get("encoder") or ""

    if not video:
        report.add(
            Finding(
                "critical",
                "NO_VIDEO",
                "No video stream found",
                "ffprobe did not report a video stream.",
                "File may be audio-only or severely corrupted.",
            )
        )

    if container.get("is_fragmented"):
        report.add(
            Finding(
                "high",
                "FRAGMENTED_MP4",
                "Fragmented MP4 (fMP4 / CMAF-style)",
                (
                    f"Found {container.get('moof_count', 0)} moof fragment(s) "
                    f"and mvex={container.get('has_mvex')}. "
                    "Many desktop players (especially older VLC builds) seek and buffer "
                    "poorly on fragmented files, while Windows Media Foundation often still plays them."
                ),
                "Remux to a progressive MP4 with interleaved A/V (fix_video.py).",
            )
        )

    if container.get("mono_track_fragments"):
        counts = container.get("fragment_sample_counts") or []
        mdats = container.get("mdat_count")
        report.add(
            Finding(
                "critical",
                "NON_INTERLEAVED_FRAGMENTS",
                "Audio and video stored in separate giant fragments",
                (
                    f"{mdats} mdat box(es); sample counts per fragment track: {counts}. "
                    "Classic symptom of HLS remux tools (e.g. videojs-contrib-hls): "
                    "all audio samples first, then all video. Seeking/start behavior becomes "
                    "player-dependent — VLC often fails or freezes; Movies & TV may limp through."
                ),
                "Remux with stream copy to a normal interleaved MP4 (+faststart).",
            )
        )

    if container.get("moov_after_mdat"):
        report.add(
            Finding(
                "medium",
                "MOOV_AT_END",
                "moov atom is after mdat",
                "Index is at the end of the file; progressive download / some players need a full read before start.",
                "Remux with -movflags +faststart.",
            )
        )

    start_time = float(fmt.get("start_time") or 0)
    if start_time > 0.1:
        report.add(
            Finding(
                "medium",
                "NONZERO_START",
                f"Container start_time is {start_time:.6f}s (not zero)",
                "Non-zero edit/timeline offsets confuse some players and A/V sync logic.",
                "Remux with timestamp regeneration (-fflags +genpts) or reset timestamps.",
            )
        )
    elif start_time > 0.01:
        report.add(
            Finding(
                "info",
                "NONZERO_START",
                f"Small start_time offset {start_time:.6f}s",
                "Common with AAC priming / H.264 B-frames; usually harmless.",
            )
        )

    for s in video:
        v_start = float(s.get("start_time") or 0)
        a_starts = [float(a.get("start_time") or 0) for a in audio]
        if a_starts and abs(v_start - a_starts[0]) > 0.05:
            report.add(
                Finding(
                    "medium",
                    "AV_START_SKEW",
                    "Audio/video start timestamps differ",
                    f"Video starts at {v_start:.6f}s, audio at {a_starts[0]:.6f}s.",
                    "Remux/fix timestamps; verify lipsync after repair.",
                )
            )
            break

    if "videojs" in encoder.lower() or "hls" in encoder.lower():
        # Only escalate when the broken HLS layout is still present.
        severe = container.get("is_fragmented") or container.get("mono_track_fragments")
        report.add(
            Finding(
                "high" if severe else "info",
                "HLS_REMUX_ENCODER",
                f"Encoder tag suggests HLS remux: {encoder!r}",
                (
                    "Files produced by HLS downloaders/remuxers frequently ship broken "
                    "or non-interleaved MP4 layouts."
                    if severe
                    else "Encoder tag is leftover metadata; container layout looks fine."
                ),
                "Treat as remux candidate even if codecs look fine." if severe else "",
            )
        )

    creation = tags.get("creation_time") or ""
    if creation.startswith("1970-01-01"):
        report.add(
            Finding(
                "low",
                "EPOCH_CREATION_TIME",
                "creation_time is Unix epoch / invalid",
                f"Tag creation_time={creation!r}. Harmless for playback but a sign of synthetic remux metadata.",
            )
        )

    for s in video:
        codec = s.get("codec_name")
        pix = s.get("pix_fmt")
        if codec == "hevc":
            report.add(
                Finding(
                    "medium",
                    "HEVC",
                    "HEVC/H.265 video",
                    "Some VLC builds/hardware paths lack a working HEVC decoder.",
                    "Transcode to H.264 if remux alone is not enough.",
                )
            )
        if pix and pix not in ("yuv420p", "yuvj420p"):
            report.add(
                Finding(
                    "medium",
                    "UNUSUAL_PIX_FMT",
                    f"Pixel format {pix}",
                    "Non-4:2:0 formats often fail in hardware decoders / picky players.",
                    "Transcode to yuv420p if needed.",
                )
            )

    for s in audio:
        codec = s.get("codec_name")
        if codec and codec not in ("aac", "mp3", "ac3", "eac3", "opus"):
            report.add(
                Finding(
                    "medium",
                    "UNUSUAL_AUDIO",
                    f"Audio codec {codec}",
                    "Less common audio codecs reduce player compatibility.",
                    "Transcode audio to AAC LC if remux is insufficient.",
                )
            )


def analyze(path: Path, *, decode_scan: bool = False) -> AnalysisReport:
    require_ffmpeg()
    if not path.is_file():
        raise FileNotFoundError(path)

    report = AnalysisReport(path=str(path.resolve()), file_size=path.stat().st_size)
    report.probe = run_ffprobe(path)

    fmt_name = (report.probe.get("format") or {}).get("format_name") or ""
    if any(x in fmt_name for x in ("mp4", "mov", "isom", "m4a", "3gp")):
        report.container = analyze_container(path)
    else:
        report.container = {"note": f"Non-MP4 container ({fmt_name}); box analysis skipped"}

    build_findings(report)

    if decode_scan:
        errors = scan_decode_errors(path)
        if errors:
            report.add(
                Finding(
                    "high",
                    "DECODE_ERRORS",
                    f"ffmpeg reported {len(errors)} decode/container error line(s)",
                    "\n".join(errors[:15]),
                    "Try remux first; if errors persist, re-encode the damaged stream.",
                )
            )
        else:
            report.add(
                Finding(
                    "info",
                    "DECODE_OK",
                    "Full decode scan reported no errors",
                    "Bitstream likely intact; problems are probably container/layout related.",
                )
            )

    report.sort()
    critical = sum(1 for f in report.findings if f.severity == "critical")
    high = sum(1 for f in report.findings if f.severity == "high")
    if critical:
        report.summary = (
            f"Likely broken for picky players ({critical} critical, {high} high). "
            "Remux to progressive interleaved MP4."
        )
    elif high:
        report.summary = (
            f"Compatibility risks detected ({high} high). Remux recommended."
        )
    elif report.findings:
        report.summary = "Minor issues only; playback should work in most players."
    else:
        report.summary = "No notable compatibility issues detected."
    return report


def print_human(report: AnalysisReport) -> None:
    print(f"File: {report.path}")
    print(f"Size: {format_size(report.file_size)}")
    fmt = report.probe.get("format") or {}
    print(
        f"Format: {fmt.get('format_name')} | duration={fmt.get('duration')}s | "
        f"bitrate={fmt.get('bit_rate')}"
    )
    for s in report.probe.get("streams") or []:
        if s.get("codec_type") == "video":
            print(
                f"  Video: {s.get('codec_name')} {s.get('width')}x{s.get('height')} "
                f"{s.get('avg_frame_rate')} fps pix={s.get('pix_fmt')} "
                f"start={s.get('start_time')}"
            )
        elif s.get("codec_type") == "audio":
            print(
                f"  Audio: {s.get('codec_name')} {s.get('sample_rate')}Hz "
                f"ch={s.get('channels')} start={s.get('start_time')}"
            )

    c = report.container
    if c.get("is_fragmented") is not None:
        print(
            f"Container: fragmented={c.get('is_fragmented')} "
            f"moof={c.get('moof_count')} mdat={c.get('mdat_count')} "
            f"mono_track_fragments={c.get('mono_track_fragments')}"
        )
        if c.get("top_level"):
            print("Top-level boxes:")
            for b in c["top_level"]:
                print(
                    f"  0x{b['offset']:08X}  {b['type']:4s}  "
                    f"{format_size(b['size'])}"
                )

    print()
    print(f"Summary: {report.summary}")
    print(f"Findings ({len(report.findings)}):")
    if not report.findings:
        print("  (none)")
        return
    for f in report.findings:
        print(f"\n  [{f.severity.upper()}] {f.code}: {f.title}")
        for line in f.detail.splitlines():
            print(f"    {line}")
        if f.fix_hint:
            print(f"    Fix: {f.fix_hint}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Diagnose why a video file plays inconsistently across players."
    )
    parser.add_argument("input", type=Path, help="Video file to analyze")
    parser.add_argument(
        "--decode-scan",
        action="store_true",
        help="Fully decode with ffmpeg (slow, catches bitstream errors)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report",
    )
    args = parser.parse_args(argv)

    try:
        report = analyze(args.input, decode_scan=args.decode_scan)
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        payload = {
            "path": report.path,
            "file_size": report.file_size,
            "summary": report.summary,
            "probe": report.probe,
            "container": report.container,
            "findings": [asdict(f) for f in report.findings],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print_human(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
