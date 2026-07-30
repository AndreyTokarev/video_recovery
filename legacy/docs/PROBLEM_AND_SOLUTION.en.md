# Why the video played in Windows but failed in VLC — and how to fix it

## Summary

`01 - Mechanics - Video 1.mp4` was **not codec-corrupted**. The failure was in the **MP4 container layout**: audio and video lived in two huge non-interleaved fragments (all audio first, then all video). That layout commonly comes from downloading / stitching an HLS stream.

- **Windows Media Player / Movies & TV** (Media Foundation) often still plays such files.
- **VLC and other stricter players** seek poorly, buffer forever, or behave unstably.

**Fix:** lossless remux into a normal progressive MP4 with interleaved A/V and `moov` at the front (`faststart`). Re-encoding is not required.

---

## Symptoms

| Observation | Notes |
|---|---|
| Opens badly in VLC / poor seeking / freezes | Typical for a “bad” fMP4 |
| Plays more or less fine in the stock Windows player | Media Foundation is more tolerant of fragmented MP4 |
| `ffprobe` reports normal H.264 + AAC | Codecs are intact |
| Full decode via `ffmpeg -f null -` reports no errors | Bitstream/frames are not rotten |

Conclusion: repair the **container**, do not re-encode the video by default.

---

## What the analysis showed

### Codecs and metadata

- Video: **H.264 High**, 1280×720, 30 fps, `yuv420p`
- Audio: **AAC LC**, 48 kHz, stereo
- Duration ≈ **18:08**
- Encoder tag: **`videojs-contrib-hls`**

The `videojs-contrib-hls` tag is a strong signal that the file was assembled from HLS segments (or a similar remux tool), not exported from a normal NLE.

### Container structure (ISO BMFF / MP4)

Top-level boxes of the original file:

```text
ftyp
moov          ← tiny, with mvex (movie extends)
moof          ← fragment #1 (mostly audio)
mdat          ← ~33 MB of audio data
moof          ← fragment #2 (video)
mdat          ← ~309 MB of video data
```

Key facts:

1. It is a **fragmented MP4 (fMP4)**: `moof` + `mvex`, not a classic full sample table inside one `moov`.
2. Only **2 fragments**, each owned by **one track**:
   - fragment 0 → audio track, **51039** samples
   - fragment 1 → video track, **32664** samples
3. Audio and video are **not interleaved** across the file timeline.
4. `creation_time` near the Unix epoch (`1970-01-01`) — typical synthetic remux metadata junk.

### Why players break

A normal progressive MP4 looks like this:

```text
ftyp
moov          ← full index (where to seek)
mdat          ← audio and video chunks interleaved by time
```

A player can:

- quickly find a keyframe;
- read audio and video in parallel;
- start playback without ingesting the whole file first.

In the broken file:

1. Starting video often means first dealing with a giant audio `mdat`.
2. Timeline seeks jump between two huge regions of the file.
3. Buffering and A/V sync become demuxer-implementation dependent.
4. VLC (and several other players) handle these “two-fragment” HLS-remux files much worse than Windows MF.

That explains the split behavior: “works on Windows, fails / almost fails in VLC”.

---

## Solution

### Approach

Repackage the container **without re-encoding** (`-c copy`):

1. Read both tracks.
2. Write a single progressive MP4.
3. Interleave audio/video by time.
4. Place the `moov` index at the front (`+faststart`).
5. Normalize timestamps (`+genpts`, `avoid_negative_ts make_zero`).

Quality and bitrate barely change: the same H.264/AAC packets are copied.

### FFmpeg command

```bash
ffmpeg -y -fflags +genpts -i "input.mp4" \
  -map 0 -c copy \
  -map_metadata -1 \
  -movflags +faststart \
  -avoid_negative_ts make_zero \
  "output_fixed.mp4"
```

### Using this repository’s tools

```bash
# Diagnose
python analyze_video.py "01 - Mechanics - Video 1.mp4"

# Fix (auto → remux)
python fix_video.py "01 - Mechanics - Video 1.mp4"
```

Output: `01 - Mechanics - Video 1_fixed.mp4`.

### After the fix

```text
ftyp
moov          ← ~1.1 MB full index at the beginning
mdat          ← one block, A/V interleaved
```

- `fragmented=False`, `moof=0`
- Single `mdat`
- Plays correctly in VLC
- Decode still reports no bitstream errors

A small `start_time` around ~0.045 s is normal for AAC priming / H.264 B-frames and is not a defect by itself.

---

## When remux is not enough

Remux fixes the **container**. If analysis/`ffmpeg` show bitstream damage, an unusual pixel format, HEVC with no player support, etc. — use **reencode**:

```bash
python fix_video.py "file.mp4" --mode reencode
```

That produces H.264 `yuv420p` + AAC LC (slower, lossy recompression).

Alternative for tolerant players: `--mode mkv` (Matroska, also stream copy).

---

## How to spot the same issue in other files

Red flags:

- encoder / handler tags like `videojs-contrib-hls`, `hls.js`, or yt-dlp/youtube-dl HLS remux without normalization;
- structure with A/V split across huge `mdat` fragments;
- tiny `moov` plus `mvex`;
- Windows plays it, VLC does not;
- `analyze_video.py` reports:
  - `NON_INTERLEAVED_FRAGMENTS` (critical)
  - `FRAGMENTED_MP4` (high)
  - `HLS_REMUX_ENCODER` (high)

Batch a folder:

```bash
python batch_videos.py . --fix
```

---

## Takeaways

| Question | Answer |
|---|---|
| Was the video “corrupt”? | No — the **packaging/layout** was |
| Why Windows OK, VLC not? | Different tolerance for fMP4 / non-interleaved fragments |
| What to do? | Remux to progressive interleaved MP4 + faststart |
| Need to re-encode? | Usually **no** |
| Main tool | `fix_video.py` / FFmpeg `-c copy -movflags +faststart` |

After remux, playback in VLC was restored for this file.
