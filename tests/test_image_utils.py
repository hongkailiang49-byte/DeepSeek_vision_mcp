import base64
import io
import json

import pytest
from PIL import Image

from config import Settings
from image_utils import (
    ImageError,
    describe_image_info,
    load_image,
)


def _make_png(width=64, height=48, color=(255, 0, 0)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


def test_load_image_from_path(tmp_path):
    p = tmp_path / "img.png"
    p.write_bytes(_make_png())
    loaded = load_image(str(p), Settings(max_pixels=1_000_000))
    assert loaded.width == 64
    assert loaded.height == 48
    assert loaded.fmt == "PNG"
    assert loaded.size_bytes == p.stat().st_size


def test_load_image_missing_file():
    with pytest.raises(ImageError, match="文件不存在"):
        load_image("C:/no/such/file.png", Settings())


def test_load_image_data_url():
    raw = _make_png()
    url = "data:image/png;base64," + base64.b64encode(raw).decode()
    loaded = load_image(url, Settings(max_pixels=1_000_000))
    assert loaded.width == 64
    assert loaded.height == 48


def test_load_image_raw_base64():
    raw = _make_png()
    loaded = load_image(base64.b64encode(raw).decode(), Settings(max_pixels=1_000_000))
    assert loaded.width == 64


def test_load_image_too_many_pixels():
    raw = _make_png(100, 100)
    with pytest.raises(ImageError, match="像素数超过限制"):
        load_image(
            "data:image/png;base64," + base64.b64encode(raw).decode(),
            Settings(max_pixels=5000),
        )


def test_describe_image_info():
    loaded = load_image(
        "data:image/png;base64," + base64.b64encode(_make_png()).decode(),
        Settings(max_pixels=1_000_000),
    )
    data = json.loads(describe_image_info(loaded))
    assert data["width"] == 64
    assert data["height"] == 48
    assert data["format"] == "PNG"
