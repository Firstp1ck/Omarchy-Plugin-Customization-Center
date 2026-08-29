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


def test_generated_png(themes_backend):
    images = helper(themes_backend, "images")
    palette = {key: "#112233" for key in "background dark_background darker_background lighter_background foreground dark_foreground light_foreground bright_foreground red yellow orange green cyan blue magenta brown accent".split()}
    data = images.encode_swatch_png(palette, 16, 16)
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert struct.unpack(">II", data[16:24]) == (16, 16)
    start = data.index(b"IDAT")
    size = int.from_bytes(data[start - 4:start], "big")
    assert len(zlib.decompress(data[start + 4:start + 4 + size])) == 16 * (1 + 16 * 3)
