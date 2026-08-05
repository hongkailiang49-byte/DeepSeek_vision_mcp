"""图片加载、校验与切片。"""
from __future__ import annotations

import base64
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from config import Settings


class ImageError(Exception):
    """面向用户的图片错误。"""


_BASE64_RE = re.compile(r"^[A-Za-z0-9+/=\r\n]+$")


@dataclass
class LoadedImage:
    source: str
    width: int
    height: int
    fmt: str
    size_bytes: int
    mode: str
    image: Image.Image


def _read_file(source: str) -> bytes:
    path = Path(source)
    if not path.is_file():
        raise ImageError(f"文件不存在：{source}")
    return path.read_bytes()


def _decode_source(source: str) -> bytes:
    if source.startswith("data:"):
        match = re.match(
            r"^data:image/[a-zA-Z0-9.+-]+;base64,(.*)$", source, re.DOTALL
        )
        if not match:
            raise ImageError("无法解析 data URL 图片")
        return base64.b64decode(match.group(1))
    if re.match(r"^https?://", source, re.IGNORECASE):
        return _download_url(source)
    if _BASE64_RE.match(source) and len(source) > 200:
        return base64.b64decode(source)
    return _read_file(source)


def load_image(source: str, settings: Settings) -> LoadedImage:
    raw = _decode_source(source)
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception as exc:
        raise ImageError(f"无法解码图片：{exc}") from exc
    if img.width * img.height > settings.max_pixels:
        raise ImageError(
            f"图片像素数超过限制（{img.width}x{img.height} > {settings.max_pixels}），"
            "可用 VISION_MAX_PIXELS 调高"
        )
    return LoadedImage(
        source=source,
        width=img.width,
        height=img.height,
        fmt=(img.format or "UNKNOWN").upper(),
        size_bytes=len(raw),
        mode=img.mode,
        image=img,
    )


def describe_image_info(loaded: LoadedImage) -> str:
    return json.dumps(
        {
            "source": loaded.source,
            "width": loaded.width,
            "height": loaded.height,
            "format": loaded.fmt,
            "size_bytes": loaded.size_bytes,
            "mode": loaded.mode,
        },
        ensure_ascii=False,
        indent=2,
    )


# _download_url 在 Task 4 实现，先提供占位以便本任务测试通过
def _download_url(url: str) -> bytes:
    raise ImageError("URL 下载将在后续任务实现")


@dataclass
class Tile:
    index: int
    box: tuple[int, int, int, int]
    image: Image.Image


def to_data_url(img: Image.Image, fmt: str = "PNG") -> str:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format=fmt)
    return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"


def resize_to_max_dim(img: Image.Image, max_dim: int) -> Image.Image:
    longest = max(img.width, img.height)
    if longest <= max_dim:
        return img
    scale = max_dim / longest
    new_size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
    return img.resize(new_size, Image.LANCZOS)


def compute_tiles(
    img: Image.Image, tile_size: int, overlap: int = 0
) -> list[Tile]:
    step_x = max(1, tile_size - overlap)
    step_y = max(1, tile_size - overlap)
    tiles: list[Tile] = []
    index = 0
    y = 0
    while y < img.height:
        x = 0
        while x < img.width:
            right = min(x + tile_size, img.width)
            bottom = min(y + tile_size, img.height)
            left = max(0, right - tile_size)
            top = max(0, bottom - tile_size)
            tiles.append(
                Tile(
                    index=index,
                    box=(left, top, right, bottom),
                    image=img.crop((left, top, right, bottom)),
                )
            )
            index += 1
            if right >= img.width:
                break
            x = right - overlap
        if bottom >= img.height:
            break
        y = bottom - overlap
    return tiles
