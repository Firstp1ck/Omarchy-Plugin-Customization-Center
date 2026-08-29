from __future__ import annotations

import binascii
import struct
import zlib
from typing import Any

_SIGNATURES = {
    "png": lambda data: data.startswith(b"\x89PNG\r\n\x1a\n"),
    "jpg": lambda data: data.startswith(b"\xff\xd8\xff"),
    "jpeg": lambda data: data.startswith(b"\xff\xd8\xff"),
    "gif": lambda data: data.startswith((b"GIF87a", b"GIF89a")),
    "bmp": lambda data: data.startswith(b"BM"),
    "webp": lambda data: len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP",
}


def image_info(data: bytes, extension: str) -> tuple[int, int]:
    ext = extension.lower().lstrip(".")
    checker = _SIGNATURES.get(ext)
    if checker is None or not checker(data):
        raise ValueError("signature")
    if ext == "png" and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if ext == "gif" and len(data) >= 10:
        return struct.unpack("<HH", data[6:10])
    if ext == "bmp" and len(data) >= 26:
        width, height = struct.unpack("<ii", data[18:26]); return abs(width), abs(height)
    if ext == "webp" and len(data) >= 30 and data[12:16] == b"VP8X":
        width = int.from_bytes(data[24:27], "little") + 1
        height = int.from_bytes(data[27:30], "little") + 1
        return width, height
    if ext in {"jpg", "jpeg"}:
        offset = 2
        while offset + 9 <= len(data):
            if data[offset] != 0xff:
                offset += 1; continue
            marker = data[offset + 1]
            if marker in {0xc0, 0xc2}:
                height, width = struct.unpack(">HH", data[offset + 5:offset + 9])
                return width, height
            if offset + 4 > len(data): break
            size = int.from_bytes(data[offset + 2:offset + 4], "big")
            offset += 2 + max(size, 2)
    raise ValueError("dimensions")


def _chunk(name: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + name + data + struct.pack(">I", binascii.crc32(name + data) & 0xffffffff)


def encode_swatch_png(palette: dict[str, Any], width: int = 480, height: int = 270) -> bytes:
    def rgb(value: str) -> bytes:
        return bytes(int(value[index:index + 2], 16) for index in (1, 3, 5))
    swatches = [palette[key] for key in ("background dark_background darker_background lighter_background foreground "
                "dark_foreground light_foreground bright_foreground red yellow orange green cyan blue magenta brown").split()]
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            color = palette["accent"] if y < 8 else swatches[min(15, x * 16 // width)] if 200 <= y < 250 else palette["background"]
            row.extend(rgb(color))
        rows.append(bytes(row))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + _chunk(b"IEND", b"")
