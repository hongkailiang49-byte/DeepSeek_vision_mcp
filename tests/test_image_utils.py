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


from image_utils import compute_tiles, resize_to_max_dim, to_data_url


def test_to_data_url_roundtrip():
    img = Image.new("RGB", (10, 10), "white")
    url = to_data_url(img)
    assert url.startswith("data:image/png;base64,")


def test_resize_to_max_dim():
    img = Image.new("RGB", (2000, 1000))
    out = resize_to_max_dim(img, 1000)
    assert out.size == (1000, 500)


def test_compute_tiles_grid():
    img = Image.new("RGB", (3000, 1000))
    tiles = compute_tiles(img, 1000, 0)
    assert len(tiles) == 3
    assert [t.box for t in tiles] == [
        (0, 0, 1000, 1000),
        (1000, 0, 2000, 1000),
        (2000, 0, 3000, 1000),
    ]


def test_compute_tiles_overlap():
    img = Image.new("RGB", (2000, 1000))
    tiles = compute_tiles(img, 1000, 100)
    assert len(tiles) == 3
    assert tiles[1].box[0] == 900


def test_compute_tiles_multi_row():
    img = Image.new("RGB", (1500, 1500))
    tiles = compute_tiles(img, 1000, 0)
    assert len(tiles) == 4
    # 边缘块贴右/下边界时左移/上移，避免切出图外
    assert tiles[3].box == (500, 500, 1500, 1500)
