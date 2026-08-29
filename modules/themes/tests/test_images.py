from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures/wallpapers"


def helper(themes_backend, name):
    return sys.modules[themes_backend.__name__ + "." + name]


def test_dimension_readers(themes_backend):
    images = helper(themes_backend, "images")
    for name in ("ok.png", "ok.jpg", "ok.gif", "ok.bmp", "ok.webp"):
        assert images.image_info((FIXTURES / name).read_bytes(), Path(name).suffix) == (16, 16)


def test_webp_vp8_vp8l_and_vp8x_dimensions(themes_backend):
    images = helper(themes_backend, "images")
    vp8_payload = b"\x00\x00\x00\x9d\x01\x2a" + (16).to_bytes(2, "little") + (17).to_bytes(2, "little")
    vp8 = b"RIFF" + (12 + len(vp8_payload)).to_bytes(4, "little") + b"WEBPVP8 " + len(vp8_payload).to_bytes(4, "little") + vp8_payload
    bits = (15 | (16 << 14)).to_bytes(4, "little")
    vp8l_payload = b"\x2f" + bits
    vp8l = b"RIFF" + (12 + len(vp8l_payload)).to_bytes(4, "little") + b"WEBPVP8L" + len(vp8l_payload).to_bytes(4, "little") + vp8l_payload
    vp8x_payload = b"\x00\x00\x00\x00" + (15).to_bytes(3, "little") + (16).to_bytes(3, "little")
    vp8x = b"RIFF" + (12 + len(vp8x_payload)).to_bytes(4, "little") + b"WEBPVP8X" + len(vp8x_payload).to_bytes(4, "little") + vp8x_payload
    assert images.image_info(vp8, ".webp") == (16, 17)
    assert images.image_info(vp8l, ".webp") == (16, 17)
    assert images.image_info(vp8x, ".webp") == (16, 17)


def test_generated_png(themes_backend):
    images = helper(themes_backend, "images")
    palette = {key: "#112233" for key in "background dark_background darker_background lighter_background foreground dark_foreground light_foreground bright_foreground red yellow orange green cyan blue magenta brown accent".split()}
    data = images.encode_swatch_png(palette, 16, 16)
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert struct.unpack(">II", data[16:24]) == (16, 16)
    start = data.index(b"IDAT")
    size = int.from_bytes(data[start - 4:start], "big")
    assert len(zlib.decompress(data[start + 4:start + 4 + size])) == 16 * (1 + 16 * 3)
