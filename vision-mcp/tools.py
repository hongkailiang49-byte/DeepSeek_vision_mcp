"""9 个 MCP 工具定义。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from cache import ResultCache
from config import Settings
from image_utils import (
    ImageError,
    LoadedImage,
    compute_tiles,
    describe_image_info,
    load_image,
    resize_to_max_dim,
)
from mineru import MinerUClient, MinerUError
from prompts import build_prompt
from providers import ProviderError, get_provider


def _error_text(exc: Exception) -> str:
    if isinstance(exc, (ImageError, ProviderError, MinerUError, ValueError)):
        return f"错误：{exc}"
    return f"错误：发生未预期异常（{type(exc).__name__}）：{exc}"


async def _analyze_loaded(
    settings: Settings,
    loaded: LoadedImage,
    scene: str,
    prompt: str = "",
    force_tile: bool = False,
    tile_size: int = 0,
) -> str:
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


async def _analyze(
    settings: Settings,
    source: str,
    scene: str,
    prompt: str = "",
    force_tile: bool = False,
    tile_size: int = 0,
) -> str:
    loaded = load_image(source, settings)
    return await _analyze_loaded(
        settings, loaded, scene, prompt, force_tile, tile_size
    )


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


def _fmt_mineru_result(result: dict, max_chars: int = 30_000) -> str:
    if result.get("state") != "done":
        lines = [f"MinerU 任务已提交（state={result.get('state')}）"]
        if result.get("task_id"):
            lines.append(f"task_id：{result['task_id']}")
        if result.get("batch_id"):
            lines.append(f"batch_id：{result['batch_id']}")
        lines.append(result.get("message", "可稍后调用 parse_document_status 查询。"))
        return "\n".join(lines)
    lines = ["MinerU 解析完成"]
    if result.get("source"):
        lines.append(f"来源：{result['source']}")
    if result.get("md_path"):
        lines.append(f"Markdown 已保存：{result['md_path']}")
    md = result.get("markdown", "")
    if len(md) > max_chars:
        lines.append(f"（内容较长，仅显示前 {max_chars} 字符）")
        md = md[:max_chars]
    lines.append("")
    lines.append(md)
    return "\n".join(lines)


_DETECT_PROMPT = (
    "请判断这张图片最像哪一类，只回答一个词，不要解释："
    "general（普通照片/风景/物体）、ui（界面/网页/软件截图）、"
    "table（表格/账单/Excel 截图）、ocr（纯文字/扫描件/文档文字）、"
    "chart（图表/曲线/柱状图/饼图）、slide（幻灯片/演示文稿页面）、"
    "document（文档/论文页面）、poster（海报/宣传图）"
)

_SCENE_ALIASES = {
    "ocr": {"ocr", "text", "文字", "扫描"},
    "table": {"table", "表格", "excel"},
    "ui": {"ui", "界面", "screenshot", "截图", "app", "web", "设计稿"},
    "chart": {"chart", "graph", "图表", "plot", "曲线"},
    "slide": {"slide", "ppt", "幻灯片", "演示"},
    "document": {"document", "doc", "文档", "page"},
    "poster": {"poster", "海报"},
}


def _normalize_scene(raw: str) -> str:
    text = (raw or "").strip().lower().strip(".:：。，,、-—*# ")
    scenes = ("general", "ui", "table", "ocr", "chart", "slide", "document", "poster")
    if text in scenes:
        return text
    for scene, words in _SCENE_ALIASES.items():
        if any(word in text for word in words):
            return scene
    return "general"


async def auto_analyze(settings: Settings, source: str, hint: str = "") -> str:
    loaded = load_image(source, settings)
    provider = get_provider(settings)
    cache = ResultCache(settings)

    scene = _normalize_scene(hint) if hint.strip() else ""
    if not scene:
        detected = await provider.complete(_DETECT_PROMPT, [loaded.image])
        scene = _normalize_scene(detected)

    key = ResultCache.key_for(source, scene)
    cached = cache.get(key)
    if cached is not None:
        return f"【缓存】{scene} 分析结果：\n{cached}"

    result = await _analyze_loaded(settings, loaded, scene)
    cache.put(key, result)
    return f"图片类型：{scene}\n\n{result}"


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

    @mcp.tool()
    async def parse_document(
        source: str,
        model_version: str = "",
        is_ocr: bool = False,
        enable_table: bool = True,
        enable_formula: bool = True,
        language: str = "ch",
        page_ranges: str = "",
        save_md: bool = True,
        out_dir: str = "",
        max_wait_s: int = 0,
    ) -> str:
        """用 MinerU 将 PDF/Word/PPT/图片/HTML 解析为 Markdown（本地路径或 URL）。"""
        try:
            client = MinerUClient(settings)
            wait = max_wait_s if max_wait_s > 0 else settings.mineru_max_wait_s
            result = await client.parse(
                source,
                out_dir=Path(out_dir) if out_dir.strip() else None,
                save_md=save_md,
                max_wait_s=wait,
                model_version=model_version,
                is_ocr=is_ocr,
                enable_table=enable_table,
                enable_formula=enable_formula,
                language=language,
                page_ranges=page_ranges,
            )
            return _fmt_mineru_result(result)
        except Exception as exc:
            return _error_text(exc)

    @mcp.tool()
    async def parse_document_status(task_id: str = "", batch_id: str = "") -> str:
        """查询 MinerU 文档解析任务状态（parse_document 返回 pending 时使用）。"""
        try:
            client = MinerUClient(settings)
            info = await client.status(task_id=task_id, batch_id=batch_id)
            return json.dumps(info, ensure_ascii=False, indent=2)
        except Exception as exc:
            return _error_text(exc)

    @mcp.tool()
    async def analyze_any(source: str, hint: str = "") -> str:
        """自动识别图片：先判断类型（UI/表格/OCR/图表/文档/海报/通用）再按场景分析。hint 可选，已知类型时跳过判断。"""
        try:
            return await auto_analyze(settings, source, hint)
        except Exception as exc:
            return _error_text(exc)
