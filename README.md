# Video Recovery

[Русский](README.ru.md)

Batch repair tool for course videos with broken **MP4 containers** (HLS remux / non-interleaved fMP4) — files that play in Windows but fail in VLC.

Default fix is a **lossless remux** (`-c copy` + `faststart`), with no re-encoding.

## What it fixes

Typical signs of broken course files:

- encoder tags like `videojs-contrib-hls`
- fragmented MP4 (`moof` / `mvex`)
- audio and video in two huge non-interleaved fragments

Details: [legacy/docs/PROBLEM_AND_SOLUTION.en.md](legacy/docs/PROBLEM_AND_SOLUTION.en.md).

## Requirements

- Python **3.12+** and [uv](https://docs.astral.sh/uv/)
- **FFmpeg** (`ffmpeg` + `ffprobe` on PATH, or in `bin/` next to the project/binary)

## Development setup

```bash
uv sync
```

Download FFmpeg into `bin/` (Windows):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/fetch_ffmpeg.ps1
```

## GUI

```bash
uv run video-recovery gui
# or
uv run video-recovery-gui
```

In the UI:

1. Select the course folder
2. **Analyze only** — diagnose without writing files
3. **Fix files** — write `*_fixed.mp4` (or replace the original with a `.bak`)

By default only files with `critical` / `high` findings are fixed.

## CLI

```bash
# Single file
uv run video-recovery analyze "lesson.mp4"
uv run video-recovery fix "lesson.mp4"
uv run video-recovery fix "lesson.mp4" --mode remux

# Course folder
uv run video-recovery batch "D:\courses\mechanics" --fix
uv run video-recovery batch "D:\courses\mechanics" --fix --force-all
```

## Windows binary

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1
```

Output: `dist/VideoRecovery/VideoRecovery.exe` (plus `ffmpeg.exe` / `ffprobe.exe` if present in `bin/`).

Zip the whole `dist/VideoRecovery` folder for distribution.

Release builds: push a `v*` tag (or run the **Build Windows** workflow). Artifacts land on [Releases](https://github.com/AndreyTokarev/video_recovery/releases).

## Layout

```text
src/video_recovery/   # package (analyze / fix / batch / gui)
legacy/               # original scripts and problem write-up
scripts/              # fetch FFmpeg, build Windows
```

## License

MIT
