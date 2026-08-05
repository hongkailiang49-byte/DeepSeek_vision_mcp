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
