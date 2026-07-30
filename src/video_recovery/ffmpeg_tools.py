"""Locate ffmpeg/ffprobe for CLI, GUI, and frozen Windows builds."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _candidate_dirs() -> list[Path]:
    dirs: list[Path] = []
    if getattr(sys, "frozen", False):
        # PyInstaller onedir / onefile
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            dirs.append(Path(meipass))
            dirs.append(Path(meipass) / "ffmpeg")
        dirs.append(Path(sys.executable).resolve().parent)
        dirs.append(Path(sys.executable).resolve().parent / "ffmpeg")
    else:
        # Dev: repo-root/bin or next to package
        pkg = Path(__file__).resolve().parent
        dirs.append(pkg.parent.parent / "bin")
        dirs.append(pkg.parent.parent / "ffmpeg")
    env = os.environ.get("VIDEO_RECOVERY_FFMPEG_DIR")
    if env:
        dirs.insert(0, Path(env))
    return dirs


def _find_tool(name: str) -> str | None:
    exe = f"{name}.exe" if sys.platform == "win32" else name
    for directory in _candidate_dirs():
        candidate = directory / exe
        if candidate.is_file():
            return str(candidate)
    return shutil.which(name)


def ffmpeg_path() -> str | None:
    return _find_tool("ffmpeg")


def ffprobe_path() -> str | None:
    return _find_tool("ffprobe")


def require_ffmpeg() -> tuple[str, str]:
    ffmpeg = ffmpeg_path()
    ffprobe = ffprobe_path()
    missing: list[str] = []
    if not ffmpeg:
        missing.append("ffmpeg")
    if not ffprobe:
        missing.append("ffprobe")
    if missing:
        raise RuntimeError(
            f"Missing required tools: {', '.join(missing)}. "
            "Install FFmpeg and ensure it is on PATH, or place ffmpeg.exe / "
            "ffprobe.exe next to the application (or in VIDEO_RECOVERY_FFMPEG_DIR)."
        )
    return ffmpeg, ffprobe
