# Vision MCP 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `vision-mcp/` 下实现一个 Python 视觉识别 MCP，提供 9 个工具，默认免费调用智谱 GLM-4V-Flash，支持多后端与大图自动切片。

**Architecture:** 官方 MCP SDK（FastMCP）+ 模块化小包。`main.py` 加载配置并注册工具；`tools.py` 定义 9 个 MCP 工具；`image_utils.py` 负责图片加载/校验/切片；`providers.py` 封装 OpenAI 兼容、Gemini、mock 三种后端；`prompts.py` 存放场景提示词。

**Tech Stack:** Python 3.12、mcp SDK 1.27、Pillow、httpx、openpyxl、pytest。

**对规格结构的补充（实现时采用）：** 新增 `config.py`（集中解析 .env 与环境变量，规格中"main.py 加载 .env"由它实现）、`tests/`（pytest 单元测试）、`scripts/smoke_test.py`（真实 API 冒烟测试）。其余结构严格遵循 [规格文档](../specs/2026-08-05-vision-mcp-design.md)。

**环境前提：** 工作区 `D:\XingKe_Total_Work\codex视觉识别` 已是 git 仓库（首提交 `525940b`）；Python 3.12.8、mcp 1.27.2 已可用；未安装的依赖由 pip 安装。

---

## 文件结构

```text
vision-mcp/
├── main.py              # MCP 入口
├── config.py            # Settings 数据类 + .env/环境变量加载
├── image_utils.py       # 加载/校验/URL 下载(SSRF)/切片
├── prompts.py           # 场景提示词
├── providers.py         # OpenAI 兼容 / Gemini / Mock 后端
├── tools.py             # 9 个 MCP 工具 + 错误包装 + xlsx 导出
├── requirements.txt
├── .env.example
├── .env                 # 真实 key，gitignore，不提交
├── README.md
├── output/              # 运行时导出，gitignore
tests/
├── test_config.py
├── test_image_utils.py
├── test_providers.py
├── test_prompts.py
└── test_tools.py
scripts/
└── smoke_test.py
```

---

### Task 1: 项目脚手架 + config.py

**Files:**
- Create: `vision-mcp/requirements.txt`
- Create: `vision-mcp/.env.example`
- Create: `vision-mcp/config.py`
- Create: `conftest.py`（工作区根目录，让 pytest 能 import vision-mcp 下的模块）
- Test: `tests/test_config.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_config.py
import os

from config import Settings, load_settings


def test_load_settings_uses_defaults(monkeypatch, tmp_path):
    for name in list(os.environ):
        if name.startswith("VISION_") or name == "ZHIPU_API_KEY":
            monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text("# empty\n", encoding="utf-8")
    settings = load_settings(env)
    assert settings.model == "glm-4v-flash"
    assert settings.provider == "auto"
    assert settings.auto_tile is True
    assert settings.timeout_ms == 60_000


def test_load_settings_reads_env_file(monkeypatch, tmp_path):
    for name in list(os.environ):
        if name.startswith("VISION_") or name == "ZHIPU_API_KEY":
            monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "ZHIPU_API_KEY=sk-test\n"
        "VISION_MODEL=glm-4v-flash\n"
        "VISION_AUTO_TILE=0\n"
        "VISION_TIMEOUT_MS=30000\n",
        encoding="utf-8",
    )
    settings = load_settings(env)
    assert settings.zhipu_api_key == "sk-test"
    assert settings.auto_tile is False
    assert settings.timeout_ms == 30_000


def test_env_overrides_dotenv(monkeypatch, tmp_path):
    monkeypatch.setenv("VISION_MODEL", "qwen-vl-plus")
    env = tmp_path / ".env"
    env.write_text("VISION_MODEL=glm-4v-flash\n", encoding="utf-8")
    settings = load_settings(env)
    assert settings.model == "qwen-vl-plus"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'config'`

- [ ] **Step 3: 创建 requirements.txt、.env.example、config.py**

```text
# vision-mcp/requirements.txt
mcp>=1.27
pillow>=10.0
httpx>=0.27
openpyxl>=3.1
pytest>=8.0
```

```text
# vision-mcp/.env.example
# 智谱 GLM-4V-Flash（默认，免费）
ZHIPU_API_KEY=

# 后端选择: auto | openai | gemini | mock
VISION_PROVIDER=auto
VISION_API_BASE=https://open.bigmodel.cn/api/paas/v4/
VISION_API_KEY=
VISION_MODEL=glm-4v-flash

VISION_TIMEOUT_MS=60000
VISION_MAX_TOKENS=4096
VISION_MAX_PIXELS=50000000
VISION_AUTO_TILE=1
VISION_AUTO_TILE_THRESHOLD=4096
VISION_TILE_SIZE=1536
VISION_TILE_OVERLAP=64
VISION_MAX_DIM=10000
VISION_MOCK=0
VISION_OUTPUT_DIR=output
```

```python
# conftest.py（工作区根目录）
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "vision-mcp"))
```

```python
# vision-mcp/config.py
"""配置加载：.env 与环境变量，环境变量优先。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: Path) -> None:
    """最小 .env 解析器，不覆盖已存在的环境变量。"""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip())
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    zhipu_api_key: str = ""
    provider: str = "auto"
    api_base: str = "https://open.bigmodel.cn/api/paas/v4/"
    api_key: str = ""
    model: str = "glm-4v-flash"
    timeout_ms: int = 60_000
    max_tokens: int = 4096
    max_pixels: int = 50_000_000
    auto_tile: bool = True
    tile_threshold: int = 4096
    tile_size: int = 1536
    tile_overlap: int = 64
    max_dim: int = 10_000
    mock: bool = False
    output_dir: Path = Path("output")


def load_settings(env_path: Path | None = None) -> Settings:
    env_path = env_path or Path(__file__).resolve().parent / ".env"
    load_dotenv(env_path)

    raw_out = os.environ.get("VISION_OUTPUT_DIR", "output").strip() or "output"
    out = Path(raw_out)
    if not out.is_absolute():
        out = Path(__file__).resolve().parent / out

    return Settings(
        zhipu_api_key=os.environ.get("ZHIPU_API_KEY", "").strip(),
        provider=os.environ.get("VISION_PROVIDER", "auto").strip().lower() or "auto",
        api_base=os.environ.get(
            "VISION_API_BASE", "https://open.bigmodel.cn/api/paas/v4/"
        ).strip(),
        api_key=os.environ.get("VISION_API_KEY", "").strip(),
        model=os.environ.get("VISION_MODEL", "glm-4v-flash").strip(),
        timeout_ms=_env_int("VISION_TIMEOUT_MS", 60_000),
        max_tokens=_env_int("VISION_MAX_TOKENS", 4096),
        max_pixels=_env_int("VISION_MAX_PIXELS", 50_000_000),
        auto_tile=_env_bool("VISION_AUTO_TILE", True),
        tile_threshold=_env_int("VISION_AUTO_TILE_THRESHOLD", 4096),
        tile_size=_env_int("VISION_TILE_SIZE", 1536),
        tile_overlap=_env_int("VISION_TILE_OVERLAP", 64),
        max_dim=_env_int("VISION_MAX_DIM", 10_000),
        mock=_env_bool("VISION_MOCK", False),
        output_dir=out,
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_config.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add vision-mcp/requirements.txt vision-mcp/.env.example vision-mcp/config.py conftest.py tests/test_config.py
git commit -m "feat(config): add settings loading for vision-mcp"
```

---

### Task 2: image_utils 基础加载与信息

**Files:**
- Create: `vision-mcp/image_utils.py`
- Test: `tests/test_image_utils.py`

- [ ] **Step 1: 写失败测试（本地路径 / data URL / base64 / 像素上限 / 信息输出）**

```python
# tests/test_image_utils.py
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_image_utils.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'image_utils'`

- [ ] **Step 3: 实现 image_utils.py 基础部分**

```python
# vision-mcp/image_utils.py
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_image_utils.py -v`
Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
git add vision-mcp/image_utils.py tests/test_image_utils.py
git commit -m "feat(image): add basic image loading and info"
```

---

### Task 3: image_utils 缩放与切片

**Files:**
- Modify: `vision-mcp/image_utils.py`
- Modify: `tests/test_image_utils.py`

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/test_image_utils.py 末尾
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
    assert tiles[3].box == (1000, 1000, 1500, 1500)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_image_utils.py -v`
Expected: FAIL，`ImportError: cannot import name 'compute_tiles'`

- [ ] **Step 3: 实现缩放、data URL、切片**

```python
# 追加到 vision-mcp/image_utils.py

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
                Tile(index=index, box=(left, top, right, bottom), image=img.crop((left, top, right, bottom)))
            )
            index += 1
            if right >= img.width:
                break
            x = right - overlap
        if bottom >= img.height:
            break
        y = bottom - overlap
    return tiles
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_image_utils.py -v`
Expected: 11 passed

- [ ] **Step 5: 提交**

```bash
git add vision-mcp/image_utils.py tests/test_image_utils.py
git commit -m "feat(image): add resizing, data-url, and tiling"
```

---

### Task 4: image_utils URL 下载与 SSRF 防护

**Files:**
- Modify: `vision-mcp/image_utils.py`
- Modify: `tests/test_image_utils.py`

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/test_image_utils.py 末尾
import socket

import httpx

from image_utils import _host_is_blocked


def test_host_is_blocked():
    assert _host_is_blocked("127.0.0.1")
    assert _host_is_blocked("10.0.0.5")
    assert _host_is_blocked("192.168.1.1")
    assert _host_is_blocked("169.254.169.254")
    assert _host_is_blocked("::1")
    assert _host_is_blocked("localhost")


def test_host_public_not_blocked():
    assert not _host_is_blocked("8.8.8.8")


def test_url_download(monkeypatch):
    png = _make_png()

    class FakeResp:
        status_code = 200
        content = png

        def raise_for_status(self):
            return None

    monkeypatch.setattr(httpx, "get", lambda *a, **k: FakeResp())
    loaded = load_image("https://example.com/a.png", Settings(max_pixels=1_000_000))
    assert loaded.width == 64


def test_url_download_blocked_private_ip():
    with pytest.raises(ImageError, match="SSRF"):
        load_image("http://169.254.169.254/latest/meta-data", Settings())
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_image_utils.py -v`
Expected: FAIL，`ImportError: cannot import name '_host_is_blocked'`

- [ ] **Step 3: 实现 URL 下载与 SSRF 防护（替换占位 `_download_url`）**

```python
# 追加到 vision-mcp/image_utils.py（并把 _decode_source 中的 _download_url 调用保留）
import ipaddress
import socket

import httpx


def _host_is_blocked(host: str) -> bool:
    host = host.strip().lower().rstrip(".")
    if not host or host == "localhost":
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ):
            return True
    return False


def _download_url(url: str, timeout: float = 30.0) -> bytes:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ImageError("仅支持 http/https 图片 URL")
    if _host_is_blocked(parsed.hostname or ""):
        raise ImageError("该 URL 指向内网/本地地址，已拦截（SSRF 防护）")
    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        return resp.content
    except httpx.HTTPError as exc:
        raise ImageError(f"下载图片失败：{exc}") from exc
```

**注意：** `_host_is_blocked` 对 `8.8.8.8` 返回 False；本机无该地址的入站连接需求，测试只校验判定函数。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_image_utils.py -v`
Expected: 15 passed

- [ ] **Step 5: 提交**

```bash
git add vision-mcp/image_utils.py tests/test_image_utils.py
git commit -m "feat(image): add URL download with SSRF protection"
```

---

### Task 5: prompts.py 场景提示词

**Files:**
- Create: `vision-mcp/prompts.py`
- Test: `tests/test_prompts.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_prompts.py
import pytest

from prompts import SCENES, build_prompt, template_for


def test_scene_set_has_required_scenes():
    assert {
        "general",
        "ui",
        "table",
        "slide",
        "document",
        "poster",
        "chart",
        "ocr",
        "compare",
    } <= SCENES


def test_template_for_all_scenes():
    for scene in SCENES:
        text = template_for(scene)
        assert text
        assert "图片" in text or "截图" in text or "图表" in text or "海报" in text


def test_template_contains_scene_specific_markers():
    assert "Markdown 表格" in template_for("table")
    assert "组件树" in template_for("ui")
    assert "图表类型" in template_for("chart")
    assert "差异" in template_for("compare")


def test_build_prompt_appends_user_prompt():
    text = build_prompt("table", "只要前 3 行")
    assert "补充要求：只要前 3 行" in text


def test_unknown_scene_raises():
    with pytest.raises(ValueError, match="未知场景"):
        template_for("nope")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_prompts.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'prompts'`

- [ ] **Step 3: 实现 prompts.py**

```python
# vision-mcp/prompts.py
"""场景提示词模板。"""
from __future__ import annotations

SCENES = {
    "general",
    "ui",
    "table",
    "slide",
    "document",
    "poster",
    "chart",
    "ocr",
    "compare",
}

_TEMPLATES: dict[str, str] = {
    "general": "请详细描述这张图片的内容，包括主体、场景、文字、颜色与风格。",
    "ocr": "请提取图片中的全部文字，按从左到右、从上到下的顺序输出文本块；"
    "不要漏掉小字，不要编造不存在的文字。",
    "table": "请把图片中的表格完整转换为 Markdown 表格，保留表头和所有行列，"
    "不要改动任何数值；如存在合并单元格请用注释说明。",
    "ui": "请分析这个 UI 截图：1) 组件树（缩进列表）；2) 布局结构；"
    "3) 设计 token（颜色/字体/间距）；4) 可落地的前端还原建议。",
    "slide": "请分析这一页幻灯片/文档：1) 标题；2) 要点列表；"
    "3) 图表或图片清单；4) 配色与排版风格；5) 输出 Markdown 大纲。",
    "document": "请分析这个文档页面：提取标题、段落结构、列表、表格和图片说明。",
    "poster": "请分析这张海报：主题、视觉风格、颜色、字体、构图、内含文字。",
    "chart": "请解读这个图表：图表类型、关键数据点、趋势、异常，并给出一句话结论。",
    "compare": "请对比两张图片，列出差异（结构/样式/内容），按严重程度排序。",
}


def template_for(scene: str) -> str:
    scene = scene.strip().lower()
    if scene not in SCENES:
        raise ValueError(f"未知场景：{scene}，可选：{', '.join(sorted(SCENES))}")
    return _TEMPLATES[scene]


def build_prompt(scene: str, user_prompt: str = "") -> str:
    base = template_for(scene)
    if user_prompt.strip():
        return f"{base}\n\n补充要求：{user_prompt.strip()}"
    return base
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_prompts.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add vision-mcp/prompts.py tests/test_prompts.py
git commit -m "feat(prompts): add scene templates"
```

---

### Task 6: providers OpenAI 兼容后端

**Files:**
- Create: `vision-mcp/providers.py`
- Test: `tests/test_providers.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_providers.py
import asyncio

from PIL import Image

from config import Settings
from providers import OpenAICompatibleProvider, ProviderError


class FakeResponse:
    def __init__(self, status_code=200, text="", data=None):
        self.status_code = status_code
        self._text = text
        self._data = data

    @property
    def text(self):
        return self._text

    def json(self):
        return self._data


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = 0
        self.last_kwargs = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        return self.responses[min(self.calls - 1, len(self.responses) - 1)]


def test_payload_shape():
    settings = Settings(api_key="k", model="glm-4v-flash")
    provider = OpenAICompatibleProvider(settings)
    img = Image.new("RGB", (10, 10))
    payload = provider._payload("describe", [img])
    assert payload["model"] == "glm-4v-flash"
    assert payload["messages"][0]["content"][0] == {"type": "text", "text": "describe"}
    assert payload["messages"][0]["content"][1]["type"] == "image_url"
    assert payload["messages"][0]["content"][1]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )


def test_success_returns_content(monkeypatch):
    ok = FakeResponse(200, data={"choices": [{"message": {"content": "ok"}}]})
    client = FakeClient([ok])
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: client)

    async def run():
        provider = OpenAICompatibleProvider(Settings(api_key="k", timeout_ms=1000))
        return await provider.complete("hi", [Image.new("RGB", (4, 4))])

    assert asyncio.run(run()) == "ok"
    assert client.calls == 1


def test_retry_on_429_then_success(monkeypatch):
    ok = FakeResponse(200, data={"choices": [{"message": {"content": "ok"}}]})
    client = FakeClient([FakeResponse(429, text="slow"), ok])
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: client)

    async def run():
        provider = OpenAICompatibleProvider(Settings(api_key="k", timeout_ms=1000))
        return await provider.complete("hi", [Image.new("RGB", (4, 4))])

    assert asyncio.run(run()) == "ok"
    assert client.calls == 2


def test_failure_raises_provider_error(monkeypatch):
    bad = FakeResponse(401, text="unauthorized")
    client = FakeClient([bad])
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: client)

    async def run():
        provider = OpenAICompatibleProvider(Settings(api_key="k", timeout_ms=1000))
        return await provider.complete("hi", [Image.new("RGB", (4, 4))])

    try:
        asyncio.run(run())
        raise AssertionError("should have raised")
    except ProviderError as exc:
        assert "401" in str(exc)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_providers.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'providers'`

- [ ] **Step 3: 实现 providers.py（OpenAI 兼容部分）**

```python
# vision-mcp/providers.py
"""视觉后端：OpenAI 兼容 / Gemini / Mock。"""
from __future__ import annotations

import asyncio
import base64
import io

import httpx
from PIL import Image

from config import Settings


class ProviderError(Exception):
    """面向用户的后端错误。"""


def _img_data_url(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"


class BaseProvider:
    async def complete(self, prompt: str, images: list[Image.Image]) -> str:
        raise NotImplementedError


class OpenAICompatibleProvider(BaseProvider):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _headers(self) -> dict[str, str]:
        key = self.settings.api_key or self.settings.zhipu_api_key
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    def _payload(self, prompt: str, images: list[Image.Image]) -> dict:
        content: list[dict] = [{"type": "text", "text": prompt}]
        for img in images:
            content.append({"type": "image_url", "image_url": {"url": _img_data_url(img)}})
        return {
            "model": self.settings.model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": self.settings.max_tokens,
        }

    async def complete(self, prompt: str, images: list[Image.Image]) -> str:
        url = self.settings.api_base.rstrip("/") + "/chat/completions"
        headers = self._headers()
        payload = self._payload(prompt, images)
        timeout = self.settings.timeout_ms / 1000
        async with httpx.AsyncClient(timeout=timeout) as client:
            for attempt in range(3):
                try:
                    resp = await client.post(url, headers=headers, json=payload)
                except httpx.HTTPError as exc:
                    if attempt < 2:
                        await asyncio.sleep(1.5**attempt)
                        continue
                    raise ProviderError(f"请求失败：{exc}") from exc
                if resp.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                    await asyncio.sleep(1.5**attempt)
                    continue
                if resp.status_code >= 400:
                    raise ProviderError(
                        f"上游返回 {resp.status_code}：{resp.text[:300]}"
                    )
                try:
                    data = resp.json()
                except ValueError as exc:
                    raise ProviderError("上游返回非 JSON 响应") from exc
                try:
                    text = data["choices"][0]["message"]["content"]
                except (KeyError, IndexError, TypeError) as exc:
                    raise ProviderError(f"响应结构异常：{data}") from exc
                if not text:
                    raise ProviderError("模型返回了空内容")
                return str(text).strip()
        raise ProviderError("上游重试后仍失败")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_providers.py -v`
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add vision-mcp/providers.py tests/test_providers.py
git commit -m "feat(providers): add OpenAI-compatible backend with retry"
```

---

### Task 7: providers Gemini 与 Mock 后端

**Files:**
- Modify: `vision-mcp/providers.py`
- Modify: `tests/test_providers.py`

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/test_providers.py 末尾
from providers import GeminiProvider, MockProvider, get_provider


def test_get_provider_mock():
    assert isinstance(get_provider(Settings(mock=True)), MockProvider)


def test_get_provider_gemini():
    assert isinstance(get_provider(Settings(provider="gemini", api_key="k")), GeminiProvider)


def test_get_provider_auto():
    assert isinstance(
        get_provider(Settings(provider="auto", api_key="k")),
        OpenAICompatibleProvider,
    )


def test_mock_complete():
    async def run():
        provider = MockProvider(Settings(mock=True))
        return await provider.complete("hi", [Image.new("RGB", (4, 4))])

    text = asyncio.run(run())
    assert "[mock]" in text
    assert "4x4" in text


def test_gemini_payload_flow(monkeypatch):
    ok = FakeResponse(
        200,
        data={"candidates": [{"content": {"parts": [{"text": "gemini ok"}]}}]},
    )
    client = FakeClient([ok])
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: client)

    async def run():
        provider = GeminiProvider(Settings(provider="gemini", api_key="k", timeout_ms=1000))
        return await provider.complete("hi", [Image.new("RGB", (4, 4))])

    assert asyncio.run(run()) == "gemini ok"
    assert client.last_kwargs["params"] == {"key": "k"}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_providers.py -v`
Expected: FAIL，`ImportError: cannot import name 'GeminiProvider'`

- [ ] **Step 3: 追加 Gemini、Mock、工厂函数**

```python
# 追加到 vision-mcp/providers.py

class GeminiProvider(BaseProvider):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def complete(self, prompt: str, images: list[Image.Image]) -> str:
        key = self.settings.api_key or self.settings.zhipu_api_key
        if not key:
            raise ProviderError("缺少 Gemini API key（VISION_API_KEY）")
        model = self.settings.model or "gemini-2.5-flash"
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        parts: list[dict] = [{"text": prompt}]
        for img in images:
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="PNG")
            parts.append(
                {
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": base64.b64encode(buf.getvalue()).decode(),
                    }
                }
            )
        payload = {"contents": [{"parts": parts}]}
        timeout = self.settings.timeout_ms / 1000
        async with httpx.AsyncClient(timeout=timeout) as client:
            for attempt in range(3):
                try:
                    resp = await client.post(url, params={"key": key}, json=payload)
                except httpx.HTTPError as exc:
                    if attempt < 2:
                        await asyncio.sleep(1.5**attempt)
                        continue
                    raise ProviderError(f"Gemini 请求失败：{exc}") from exc
                if resp.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                    await asyncio.sleep(1.5**attempt)
                    continue
                if resp.status_code >= 400:
                    raise ProviderError(f"Gemini 返回 {resp.status_code}：{resp.text[:300]}")
                data = resp.json()
                try:
                    text = data["candidates"][0]["content"]["parts"][0]["text"]
                except (KeyError, IndexError, TypeError) as exc:
                    raise ProviderError(f"Gemini 响应结构异常：{data}") from exc
                if not text:
                    raise ProviderError("Gemini 返回了空内容")
                return str(text).strip()
        raise ProviderError("Gemini 重试后仍失败")


class MockProvider(BaseProvider):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def complete(self, prompt: str, images: list[Image.Image]) -> str:
        sizes = "、".join(f"{img.width}x{img.height}" for img in images)
        return f"[mock] 已收到 {len(images)} 张图片（{sizes}）。提示词：{prompt[:80]}"


def get_provider(settings: Settings) -> BaseProvider:
    if settings.mock or settings.provider == "mock":
        return MockProvider(settings)
    if settings.provider == "gemini":
        return GeminiProvider(settings)
    if settings.provider in {"auto", "openai"}:
        return OpenAICompatibleProvider(settings)
    raise ProviderError(f"未知 VISION_PROVIDER：{settings.provider}")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_providers.py -v`
Expected: 9 passed

- [ ] **Step 5: 提交**

```bash
git add vision-mcp/providers.py tests/test_providers.py
git commit -m "feat(providers): add Gemini and mock backends"
```

---

### Task 8: 9 个 MCP 工具 + 入口（mock 全通）

**Files:**
- Create: `vision-mcp/tools.py`
- Create: `vision-mcp/main.py`
- Test: `tests/test_tools.py`

- [ ] **Step 1: 写失败测试（注册 + mock 调用）**

```python
# tests/test_tools.py
import asyncio
import base64
import io

from PIL import Image
from mcp.server.fastmcp import FastMCP

from config import Settings
from tools import register_tools


def _data_url(color=(10, 20, 30), width=80, height=60):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _make_mcp():
    settings = Settings(mock=True, auto_tile=False, max_pixels=1_000_000)
    mcp = FastMCP("vision-mcp-test")
    register_tools(mcp, settings)
    return mcp


def test_all_tools_registered():
    mcp = _make_mcp()

    async def run():
        tools = await mcp.list_tools()
        return {t.name for t in tools}

    names = asyncio.run(run())
    assert names == {
        "analyze_image",
        "image_info",
        "ocr_image",
        "table_from_image",
        "analyze_ui",
        "analyze_document_slide",
        "describe_chart",
        "compare_images",
        "tile_image",
    }


def _call(mcp, name, arguments):
    async def run():
        result = await mcp.call_tool(name, arguments)
        return "".join(c.text or "" for c in result.content)

    return asyncio.run(run())


def test_analyze_image_mock():
    mcp = _make_mcp()
    text = _call(mcp, "analyze_image", {"image": _data_url(), "prompt": "是什么"})
    assert "[mock]" in text


def test_image_info_mock():
    mcp = _make_mcp()
    text = _call(mcp, "image_info", {"image": _data_url()})
    assert '"width": 80' in text
    assert '"height": 60' in text


def test_ocr_and_compare_mock():
    mcp = _make_mcp()
    ocr = _call(mcp, "ocr_image", {"image": _data_url()})
    assert "[mock]" in ocr
    cmp = _call(mcp, "compare_images", {"image_a": _data_url(), "image_b": _data_url()})
    assert "[mock]" in cmp


def test_bad_source_returns_friendly_error():
    mcp = _make_mcp()
    text = _call(mcp, "analyze_image", {"image": "C:/no/such.png"})
    assert text.startswith("错误：")
    assert "文件不存在" in text
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_tools.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'tools'`

- [ ] **Step 3: 实现 tools.py 与 main.py**

```python
# vision-mcp/tools.py
"""9 个 MCP 工具定义。"""
from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from config import Settings
from image_utils import (
    ImageError,
    LoadedImage,
    compute_tiles,
    describe_image_info,
    load_image,
    resize_to_max_dim,
)
from prompts import build_prompt
from providers import ProviderError, get_provider


def _error_text(exc: Exception) -> str:
    if isinstance(exc, (ImageError, ProviderError, ValueError)):
        return f"错误：{exc}"
    return f"错误：发生未预期异常（{type(exc).__name__}）：{exc}"


async def _analyze(
    settings: Settings,
    source: str,
    scene: str,
    prompt: str = "",
    force_tile: bool = False,
    tile_size: int = 0,
) -> str:
    loaded = load_image(source, settings)
    provider = get_provider(settings)
    user_prompt = build_prompt(scene, prompt)

    if force_tile:
        resized = loaded.image
        if settings.max_dim > 0:
            resized = resize_to_max_dim(resized, settings.max_dim)
        tiles = compute_tiles(
            resized, tile_size or settings.tile_size, settings.tile_overlap
        )
        results = []
        for tile in tiles:
            part = await provider.complete(
                f"{user_prompt}\n（这是整图的第 {tile.index + 1}/{len(tiles)} 块，"
                f"原始坐标 {tile.box}）",
                [tile.image],
            )
            results.append(f"【块 {tile.index + 1}/{len(tiles)}】{part}")
        return "\n\n".join(results)

    images = _tile_sources(settings, loaded)
    if len(images) == 1:
        return await provider.complete(user_prompt, [images[0].image])
    results = []
    for idx, item in enumerate(images, 1):
        part = await provider.complete(
            f"{user_prompt}\n（这是第 {idx}/{len(images)} 块）", [item.image]
        )
        results.append(f"【块 {idx}/{len(images)}】{part}")
    return "\n\n".join(results)


def _tile_sources(settings: Settings, loaded: LoadedImage) -> list[LoadedImage]:
    image = loaded.image
    if settings.max_dim > 0:
        image = resize_to_max_dim(image, settings.max_dim)
    if settings.auto_tile and max(image.width, image.height) > settings.tile_threshold:
        tiles = compute_tiles(image, settings.tile_size, settings.tile_overlap)
        return [
            LoadedImage(
                source=f"{loaded.source} [tile {t.index}]",
                width=t.image.width,
                height=t.image.height,
                fmt="PNG",
                size_bytes=0,
                mode=t.image.mode,
                image=t.image,
            )
            for t in tiles
        ]
    return [
        LoadedImage(
            source=loaded.source,
            width=image.width,
            height=image.height,
            fmt=loaded.fmt,
            size_bytes=loaded.size_bytes,
            mode=image.mode,
            image=image,
        )
    ]


def _parse_md_table(md: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in md.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(c.replace("-", "").replace(":", "") == "" for c in cells):
            continue
        rows.append(cells)
    return rows


def _write_xlsx(rows: list[list[str]], out_path: Path) -> str:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    wb.save(out_path)
    return str(out_path)


def register_tools(mcp: FastMCP, settings: Settings) -> None:
    @mcp.tool()
    async def analyze_image(image: str, prompt: str = "", scene: str = "general") -> str:
        try:
            return await _analyze(settings, image, scene, prompt)
        except Exception as exc:
            return _error_text(exc)

    @mcp.tool()
    async def image_info(image: str) -> str:
        try:
            return describe_image_info(load_image(image, settings))
        except Exception as exc:
            return _error_text(exc)

    @mcp.tool()
    async def ocr_image(image: str, language: str = "zh") -> str:
        try:
            return await _analyze(settings, image, "ocr", f"语言：{language}")
        except Exception as exc:
            return _error_text(exc)

    @mcp.tool()
    async def table_from_image(
        image: str, export_xlsx: bool = False, out_path: str = ""
    ) -> str:
        try:
            loaded = load_image(image, settings)
            provider = get_provider(settings)
            md = await provider.complete(build_prompt("table"), [loaded.image])
            result = f"表格识别结果：\n\n{md}"
            if export_xlsx:
                rows = _parse_md_table(md)
                if not rows:
                    result += "\n\n[警告] 未能解析出 Markdown 表格，未生成 Excel。"
                else:
                    out_dir = settings.output_dir
                    out_dir.mkdir(parents=True, exist_ok=True)
                    path = Path(out_path) if out_path.strip() else out_dir / "table_export.xlsx"
                    if not path.is_absolute():
                        path = out_dir / path
                    result += f"\n\n已导出 Excel：{_write_xlsx(rows, path)}"
            return result
        except Exception as exc:
            return _error_text(exc)

    @mcp.tool()
    async def analyze_ui(image: str, focus: str = "") -> str:
        try:
            return await _analyze(settings, image, "ui", focus)
        except Exception as exc:
            return _error_text(exc)

    @mcp.tool()
    async def analyze_document_slide(image: str, scene: str = "slide") -> str:
        try:
            if scene not in {"slide", "document", "poster"}:
                scene = "slide"
            return await _analyze(settings, image, scene)
        except Exception as exc:
            return _error_text(exc)

    @mcp.tool()
    async def describe_chart(image: str, chart_type: str = "") -> str:
        try:
            return await _analyze(settings, image, "chart", chart_type)
        except Exception as exc:
            return _error_text(exc)

    @mcp.tool()
    async def compare_images(image_a: str, image_b: str, focus: str = "") -> str:
        try:
            loaded_a = load_image(image_a, settings)
            loaded_b = load_image(image_b, settings)
            provider = get_provider(settings)
            return await provider.complete(
                build_prompt("compare", focus), [loaded_a.image, loaded_b.image]
            )
        except Exception as exc:
            return _error_text(exc)

    @mcp.tool()
    async def tile_image(image: str, tile_size: int = 0, prompt: str = "") -> str:
        try:
            return await _analyze(
                settings, image, "general", prompt, force_tile=True, tile_size=tile_size
            )
        except Exception as exc:
            return _error_text(exc)
```

```python
# vision-mcp/main.py
"""vision-mcp 入口。"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from config import load_settings
from tools import register_tools


def main() -> None:
    settings = load_settings()
    mcp = FastMCP("vision-mcp")
    register_tools(mcp, settings)
    mcp.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_tools.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add vision-mcp/tools.py vision-mcp/main.py tests/test_tools.py
git commit -m "feat(tools): register 9 vision MCP tools"
```

---

### Task 9: 自动切片行为与 tile 工具测试

**Files:**
- Modify: `tests/test_tools.py`

- [ ] **Step 1: 追加失败测试（mock 下验证切片路径）**

```python
# 追加到 tests/test_tools.py 末尾
def test_auto_tile_splits_large_image():
    settings = Settings(
        mock=True, auto_tile=True, tile_threshold=100, tile_size=64, tile_overlap=0
    )
    mcp = FastMCP("vision-mcp-test")
    register_tools(mcp, settings)
    text = _call(mcp, "analyze_image", {"image": _data_url(width=200, height=100)})
    assert "【块 1/8】" in text
    assert "【块 4/8】" in text


def test_force_tile_tool():
    settings = Settings(
        mock=True, auto_tile=False, tile_overlap=0, max_pixels=1_000_000
    )
    mcp = FastMCP("vision-mcp-test")
    register_tools(mcp, settings)
    text = _call(
        mcp,
        "tile_image",
        {"image": _data_url(width=150, height=150), "tile_size": 100},
    )
    assert "【块 1/4】" in text
    assert "【块 4/4】" in text


def test_auto_tile_off_sends_single():
    settings = Settings(mock=True, auto_tile=False, max_pixels=1_000_000)
    mcp = FastMCP("vision-mcp-test")
    register_tools(mcp, settings)
    text = _call(mcp, "analyze_image", {"image": _data_url(width=200, height=100)})
    assert "已收到 1 张图片" in text
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_tools.py -v`
Expected: `test_auto_tile_splits_large_image` 失败（mock 结果不含"【块"），因为 `_analyze` 未拆分；其余通过

- [ ] **Step 3: 运行通过——实现已在上一个任务完成，只需确认拆分逻辑被触发**

说明：`_analyze` 中 `_tile_sources` 在 `auto_tile=True` 且长边 > `tile_threshold` 时返回多块并逐块请求。若上一步意外通过，检查 `_tile_sources` 是否正确返回多块；若不通过，修正 `_tile_sources` 后重跑。

Run: `python -m pytest tests/test_tools.py -v`
Expected: 8 passed

- [ ] **Step 4: 提交**

```bash
git add tests/test_tools.py
git commit -m "test(tools): cover auto-tile and force-tile paths"
```

---

### Task 10: xlsx 导出与 table 工具测试

**Files:**
- Modify: `tests/test_tools.py`

- [ ] **Step 1: 追加失败测试（mock 后端 + 导出 Excel）**

```python
# 追加到 tests/test_tools.py 末尾
def test_table_export_xlsx(tmp_path):
    settings = Settings(
        mock=False,
        auto_tile=False,
        max_pixels=1_000_000,
        output_dir=tmp_path,
    )

    class TableMock:
        async def complete(self, prompt, images):
            return "| Name | Score |\n|---|---|\n| Alice | 92 |\n| Bob | 85 |"

    import tools as tools_module

    original = tools_module.get_provider
    tools_module.get_provider = lambda s: TableMock()
    try:
        mcp = FastMCP("vision-mcp-test")
        tools_module.register_tools(mcp, settings)
        text = _call(
            mcp,
            "table_from_image",
            {"image": _data_url(), "export_xlsx": True, "out_path": "out.xlsx"},
        )
    finally:
        tools_module.get_provider = original

    assert "表格识别结果" in text
    assert "已导出 Excel" in text
    out = tmp_path / "out.xlsx"
    assert out.is_file()

    from openpyxl import load_workbook

    ws = load_workbook(out).active
    assert ws["A1"].value == "Name"
    assert ws["B2"].value == "85"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_tools.py::test_table_export_xlsx -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'openpyxl'`（依赖未装）

- [ ] **Step 3: 安装依赖并确认实现**

Run: `python -m pip install -r vision-mcp/requirements.txt`

说明：`_parse_md_table` 与 `_write_xlsx` 已在 Task 8 实现。若安装依赖后测试仍失败，检查 `_parse_md_table` 是否正确跳过分隔行。

Run: `python -m pytest tests/test_tools.py::test_table_export_xlsx -v`
Expected: PASS

- [ ] **Step 4: 全量跑一遍**

Run: `python -m pytest tests -v`
Expected: 全部通过（约 42 个）

- [ ] **Step 5: 提交**

```bash
git add .
git commit -m "chore(deps): install and verify xlsx export path"
```

---

### Task 11: README + .env + 真实 API 冒烟测试

**Files:**
- Create: `vision-mcp/README.md`
- Create: `vision-mcp/.env`（gitignore，含真实 key，不提交）
- Create: `scripts/smoke_test.py`

- [ ] **Step 1: 写 README**

```markdown
# vision-mcp

给 Codex / Claude Code / Cursor 等 MCP 客户端使用的视觉识别服务。默认调用智谱 GLM-4V-Flash（免费），支持任意 OpenAI 兼容后端与 Gemini。

## 功能

- `analyze_image` 通用识图
- `image_info` 图片基本信息（本地计算，零成本）
- `ocr_image` 图片文字提取
- `table_from_image` 表格转 Markdown / Excel
- `analyze_ui` UI 截图分析（组件树 / 设计 token / 还原建议）
- `analyze_document_slide` 幻灯片 / 文档 / 海报分析
- `describe_chart` 图表解读
- `compare_images` 双图对比
- `tile_image` 大图切片逐块分析

## 安装

```bash
cd vision-mcp
python -m pip install -r requirements.txt
copy .env.example .env
```

编辑 `.env`，填入 `ZHIPU_API_KEY`（智谱开放平台 https://open.bigmodel.cn 免费获取，模型 `glm-4v-flash` 免费）。

## 接入 Codex

在 `~/.codex/config.toml` 添加：

```toml
[mcp_servers.vision-mcp]
command = "python"
args = ["D:/XingKe_Total_Work/codex视觉识别/vision-mcp/main.py"]
startup_timeout_sec = 60
```

如果 `python` 不在 PATH，换成 `py` 或完整 Python 路径。

## 切换后端

- OpenAI 兼容：设置 `VISION_API_BASE` / `VISION_API_KEY` / `VISION_MODEL`
- Gemini：`VISION_PROVIDER=gemini` + `VISION_API_KEY=AIza...`
- 本地 Ollama：`VISION_API_BASE=http://localhost:11434/v1`、`VISION_API_KEY=ollama`、`VISION_MODEL=llava`
- 无 key 调试：`VISION_MOCK=1`

## 常见问题

- 大图被压缩？检查 `VISION_AUTO_TILE` 与 `VISION_MAX_DIM`。
- 图片过大被拒？调高 `VISION_MAX_PIXELS`。
- 请求超时？调高 `VISION_TIMEOUT_MS`。
```

- [ ] **Step 2: 创建 .env（真实 key，gitignore 已排除）**

创建 `vision-mcp/.env`，内容基于 `.env.example`，并填入：

```text
ZHIPU_API_KEY=<用户在对话中提供的智谱 key>
```

验证：`git check-ignore vision-mcp/.env` 应输出该路径。

- [ ] **Step 3: 写冒烟测试脚本**

```python
# scripts/smoke_test.py
"""真实 API 冒烟测试：analyze_image / ocr_image / table_from_image。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "vision-mcp"))

import asyncio
import base64
import io

from PIL import Image, ImageDraw
from mcp.server.fastmcp import FastMCP

from config import load_settings
from tools import register_tools


def _table_image() -> str:
    img = Image.new("RGB", (640, 400), "white")
    d = ImageDraw.Draw(img)
    heads = ["Name", "Score", "Grade"]
    rows = [["Alice", "92", "A"], ["Bob", "85", "B"], ["Carol", "78", "C"]]
    for i, head in enumerate(heads):
        x = 40 + i * 180
        d.rectangle([x, 30, x + 170, 80], outline="black")
        d.text((x + 10, 40), head)
    for r, row in enumerate(rows):
        y = 90 + r * 70
        for c, val in enumerate(row):
            x = 40 + c * 180
            d.rectangle([x, y, x + 170, y + 55], outline="black")
            d.text((x + 10, y + 15), val)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


async def run() -> None:
    settings = load_settings()
    mcp = FastMCP("vision-smoke")
    register_tools(mcp, settings)
    img = _table_image()

    r1 = await mcp.call_tool(
        "analyze_image", {"image": img, "prompt": "用一句话描述这张图"}
    )
    print("ANALYZE:", "".join(c.text or "" for c in r1.content))

    r2 = await mcp.call_tool("ocr_image", {"image": img})
    print("OCR:", "".join(c.text or "" for c in r2.content))

    r3 = await mcp.call_tool("table_from_image", {"image": img})
    print("TABLE:", "".join(c.text or "" for c in r3.content))


if __name__ == "__main__":
    asyncio.run(run())
```

- [ ] **Step 4: 运行冒烟测试**

Run: `python scripts/smoke_test.py`
Expected: 三行输出均非空；OCR 与 TABLE 输出中出现 `Alice`、`Bob`、`Carol` 中的至少两个；ANALYZE 为一句通顺描述。

若出现 `401`：检查 `.env` 中 key 是否正确；若出现超时：调大 `VISION_TIMEOUT_MS` 后重试。

- [ ] **Step 5: 提交**

```bash
git add vision-mcp/README.md scripts/smoke_test.py
git commit -m "docs: add vision-mcp README and smoke test"
```

---

### Task 12: 全量回归 + 交付检查

**Files:**
- 无新增

- [ ] **Step 1: 全量测试**

Run: `python -m pytest tests -v`
Expected: 全部通过

- [ ] **Step 2: 检查无密钥泄漏**

Run: `git grep -n "5663cd36" -- . || echo "未发现密钥"`（或实际 key 的前 8 位）
Expected: 未发现密钥

- [ ] **Step 3: 确认 MCP 可启动**

Run: `python -c "import sys; sys.path.insert(0, 'vision-mcp'); import main; print('import ok')"`
Expected: `import ok`

- [ ] **Step 4: 最终提交**

```bash
git add .
git commit -m "chore: final regression pass for vision-mcp"
```

- [ ] **Step 5: 向用户报告，并询问是否写入 `~/.codex/config.toml`（先备份）**

交付说明：9 个工具、测试结果、冒烟测试输出、Codex 接入配置。

---

## 规格覆盖自检

- 9 个工具：Task 8（注册） + Task 9/10（行为测试）✓
- 后端层（OpenAI 兼容 / Gemini / Mock）：Task 6、Task 7 ✓
- 大图切片：Task 3（算法）、Task 9（自动/强制路径）✓
- 配置项：Task 1（全部 .env 变量）✓
- 错误处理：Task 6（重试/结构异常）、Task 8（`_error_text`）✓
- 安全：Task 4（SSRF）、Task 1（.env 解析）、Task 12（密钥泄漏检查）✓
- 测试三层：Task 1-10（单元 + mock 联调）、Task 11（真实 API）✓
- README 与 Codex 接入：Task 11 ✓
