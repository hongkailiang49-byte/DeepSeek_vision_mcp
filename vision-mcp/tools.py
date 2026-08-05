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
