"""Batch analyze / fix videos in a course folder."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from video_recovery.analyze import AnalysisReport, analyze
from video_recovery.fix import fix_file

VIDEO_EXTS = {".mp4", ".m4v", ".mov", ".mkv", ".webm", ".ts", ".m2ts", ".avi"}

LogFn = Callable[[str], None]
ProgressFn = Callable[[int, int, Path], None]


@dataclass
class BatchItemResult:
    path: Path
    status: str  # ok | skipped | fixed | failed
    message: str = ""
    report: AnalysisReport | None = None
    output: Path | None = None
    mode: str | None = None


@dataclass
class BatchResult:
    items: list[BatchItemResult] = field(default_factory=list)

    @property
    def failed(self) -> int:
        return sum(1 for i in self.items if i.status == "failed")

    @property
    def fixed(self) -> int:
        return sum(1 for i in self.items if i.status == "fixed")

    @property
    def skipped(self) -> int:
        return sum(1 for i in self.items if i.status == "skipped")


def iter_videos(root: Path, *, recursive: bool = True) -> list[Path]:
    if not root.is_dir():
        raise NotADirectoryError(root)
    iterator = root.rglob("*") if recursive else root.iterdir()
    return sorted(
        p
        for p in iterator
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS and "_fixed" not in p.stem
    )


def process_directory(
    root: Path,
    *,
    fix: bool = False,
    only_if_needed: bool = True,
    mode: str = "auto",
    recursive: bool = True,
    in_place: bool = False,
    verify_output: bool = True,
    log: LogFn | None = None,
    progress: ProgressFn | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> BatchResult:
    """Analyze (and optionally fix) all videos under ``root``."""
    _log = log or (lambda _msg: None)
    paths = iter_videos(root, recursive=recursive)
    result = BatchResult()
    total = len(paths)
    if total == 0:
        _log("No video files found.")
        return result

    for index, path in enumerate(paths, start=1):
        if should_cancel and should_cancel():
            _log("Cancelled.")
            break
        if progress:
            progress(index, total, path)
        _log(f"[{index}/{total}] {path}")
        try:
            report = analyze(path, decode_scan=False)
            _log(f"  {report.summary}")
            if not fix:
                result.items.append(
                    BatchItemResult(
                        path=path,
                        status="ok",
                        message=report.summary,
                        report=report,
                    )
                )
                continue

            if only_if_needed and not report.needs_fix():
                _log("  Skip (no critical/high issues).")
                result.items.append(
                    BatchItemResult(
                        path=path,
                        status="skipped",
                        message="No fix needed",
                        report=report,
                    )
                )
                continue

            outcome = fix_file(
                path,
                mode=mode,
                in_place=in_place,
                verify_output=verify_output,
            )
            out = Path(outcome["output"])
            v = outcome.get("verification") or {}
            _log(f"  Fixed ({outcome['mode']}) -> {out.name}")
            if v.get("summary"):
                _log(f"  Verify: {v['summary']}")
            result.items.append(
                BatchItemResult(
                    path=path,
                    status="fixed",
                    message=str(v.get("summary") or "fixed"),
                    report=report,
                    output=out,
                    mode=str(outcome["mode"]),
                )
            )
        except Exception as exc:  # noqa: BLE001
            _log(f"  FAILED: {exc}")
            result.items.append(
                BatchItemResult(path=path, status="failed", message=str(exc))
            )

    _log(
        f"Done. files={len(result.items)} fixed={result.fixed} "
        f"skipped={result.skipped} failed={result.failed}"
    )
    return result
