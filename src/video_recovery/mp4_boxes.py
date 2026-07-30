"""Minimal MP4/ISO-BMFF box parser (stdlib only)."""

from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO


CONTAINER_BOXES = frozenset(
    {
        "moov",
        "trak",
        "mdia",
        "minf",
        "stbl",
        "edts",
        "udta",
        "mvex",
        "moof",
        "traf",
        "dinf",
        "meta",
        "sinf",
        "schi",
    }
)


@dataclass
class Box:
    offset: int
    type: str
    size: int
    header_size: int
    children: list[Box] = field(default_factory=list)

    @property
    def end(self) -> int:
        return self.offset + self.size

    @property
    def payload_offset(self) -> int:
        return self.offset + self.header_size

    @property
    def payload_size(self) -> int:
        return self.size - self.header_size


def _decode_type(raw: bytes) -> str:
    try:
        return raw.decode("latin-1")
    except Exception:
        return repr(raw)


def iter_boxes(
    f: BinaryIO,
    start: int,
    end: int,
    *,
    recurse: bool = True,
    max_depth: int = 8,
    depth: int = 0,
) -> Iterator[Box]:
    offset = start
    while offset + 8 <= end:
        f.seek(offset)
        header = f.read(8)
        if len(header) < 8:
            break
        size32, type_raw = struct.unpack(">I4s", header)
        box_type = _decode_type(type_raw)
        header_size = 8
        if size32 == 1:
            large = f.read(8)
            if len(large) < 8:
                break
            size = struct.unpack(">Q", large)[0]
            header_size = 16
        elif size32 == 0:
            size = end - offset
        else:
            size = size32

        if size < header_size:
            break

        box = Box(offset=offset, type=box_type, size=size, header_size=header_size)
        if recurse and box_type in CONTAINER_BOXES and depth < max_depth:
            box.children = list(
                iter_boxes(
                    f,
                    box.payload_offset,
                    box.end,
                    recurse=True,
                    max_depth=max_depth,
                    depth=depth + 1,
                )
            )
        yield box
        offset += size


def parse_top_level(path: Path, *, recurse: bool = True) -> list[Box]:
    size = path.stat().st_size
    with path.open("rb") as f:
        return list(iter_boxes(f, 0, size, recurse=recurse))


def walk(boxes: list[Box]) -> Iterator[Box]:
    for box in boxes:
        yield box
        yield from walk(box.children)


def find_all(boxes: list[Box], box_type: str) -> list[Box]:
    return [b for b in walk(boxes) if b.type == box_type]


def read_payload(path: Path, box: Box) -> bytes:
    with path.open("rb") as f:
        f.seek(box.payload_offset)
        return f.read(box.payload_size)


def parse_tfhd(payload: bytes) -> dict:
    version = payload[0]
    flags = int.from_bytes(payload[1:4], "big")
    track_id = struct.unpack(">I", payload[4:8])[0]
    offset = 8
    info: dict = {"version": version, "flags": flags, "track_id": track_id}
    if flags & 0x1:
        info["base_data_offset"] = struct.unpack(">Q", payload[offset : offset + 8])[0]
        offset += 8
    if flags & 0x2:
        info["sample_description_index"] = struct.unpack(
            ">I", payload[offset : offset + 4]
        )[0]
        offset += 4
    if flags & 0x8:
        info["default_sample_duration"] = struct.unpack(
            ">I", payload[offset : offset + 4]
        )[0]
        offset += 4
    if flags & 0x10:
        info["default_sample_size"] = struct.unpack(">I", payload[offset : offset + 4])[
            0
        ]
        offset += 4
    if flags & 0x20:
        info["default_sample_flags"] = struct.unpack(">I", payload[offset : offset + 4])[
            0
        ]
    return info


def parse_trun(payload: bytes) -> dict:
    version = payload[0]
    flags = int.from_bytes(payload[1:4], "big")
    sample_count = struct.unpack(">I", payload[4:8])[0]
    offset = 8
    info: dict = {
        "version": version,
        "flags": flags,
        "sample_count": sample_count,
    }
    if flags & 0x1:
        info["data_offset"] = struct.unpack(">i", payload[offset : offset + 4])[0]
        offset += 4
    if flags & 0x4:
        info["first_sample_flags"] = struct.unpack(">I", payload[offset : offset + 4])[0]
        offset += 4
    return info


def parse_tfdt(payload: bytes) -> dict:
    version = payload[0]
    if version == 1:
        base = struct.unpack(">Q", payload[4:12])[0]
    else:
        base = struct.unpack(">I", payload[4:8])[0]
    return {"version": version, "base_media_decode_time": base}


def format_size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{value:.2f} TB"
