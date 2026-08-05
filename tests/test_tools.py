import asyncio
import base64
import io
import json

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
        "parse_document",
        "parse_document_status",
    }


def _call(mcp, name, arguments):
    async def run():
        result = await mcp.call_tool(name, arguments)
        if isinstance(result, tuple):
            result = result[0]
        if isinstance(result, dict):
            return json.dumps(result, ensure_ascii=False)
        return "".join(c.text or "" for c in result)

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
    assert ws["B2"].value == "92"
    assert ws["B3"].value == "85"


class FakeMinerUClient:
    def __init__(self, settings):
        self.settings = settings

    async def parse(self, source, **kwargs):
        return {
            "state": "done",
            "source": source,
            "task_id": "t1",
            "batch_id": "",
            "markdown": "# 解析结果",
            "md_path": "C:/out/full.md",
        }

    async def status(self, task_id="", batch_id=""):
        return {
            "task_id": task_id,
            "batch_id": batch_id,
            "state": "done",
            "full_zip_url": "https://z/full.zip",
        }


def test_parse_document_tool_returns_markdown(monkeypatch, tmp_path):
    import tools as tools_module

    settings = Settings(
        mineru_api_key="sk-mineru", mineru_max_wait_s=30, output_dir=tmp_path
    )
    monkeypatch.setattr(tools_module, "MinerUClient", FakeMinerUClient)
    mcp = FastMCP("vision-mcp-test")
    tools_module.register_tools(mcp, settings)
    text = _call(mcp, "parse_document", {"source": "https://example.com/a.pdf"})
    assert "MinerU 解析完成" in text
    assert "# 解析结果" in text
    assert "C:/out/full.md" in text


def test_parse_document_status_tool(monkeypatch):
    import tools as tools_module

    settings = Settings(mineru_api_key="sk-mineru")
    monkeypatch.setattr(tools_module, "MinerUClient", FakeMinerUClient)
    mcp = FastMCP("vision-mcp-test")
    tools_module.register_tools(mcp, settings)
    text = _call(mcp, "parse_document_status", {"task_id": "t1"})
    assert "t1" in text
    assert "done" in text
