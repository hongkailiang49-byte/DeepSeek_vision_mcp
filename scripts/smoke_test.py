"""真实 API 冒烟测试：analyze_image / ocr_image / table_from_image。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "vision-mcp"))

import asyncio
import base64
import io

from PIL import Image, ImageDraw, ImageFont
from mcp.server.fastmcp import FastMCP

from config import load_settings
from tools import register_tools


def _table_image() -> str:
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 28)
    except OSError:
        font = ImageFont.load_default(size=28)
    img = Image.new("RGB", (760, 420), "white")
    d = ImageDraw.Draw(img)
    heads = ["Name", "Score", "Grade"]
    rows = [["Alice", "92", "A"], ["Bob", "85", "B"], ["Carol", "78", "C"]]
    for i, head in enumerate(heads):
        x = 40 + i * 220
        d.rectangle([x, 30, x + 210, 100], outline="black")
        d.text((x + 12, 45), head, fill="black", font=font)
    for r, row in enumerate(rows):
        y = 110 + r * 80
        for c, val in enumerate(row):
            x = 40 + c * 220
            d.rectangle([x, y, x + 210, y + 70], outline="black")
            d.text((x + 12, y + 15), val, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _text(result) -> str:
    if isinstance(result, tuple):
        result = result[0]
    if isinstance(result, dict):
        import json

        return json.dumps(result, ensure_ascii=False)
    return "".join(c.text or "" for c in result)


async def run() -> None:
    settings = load_settings()
    mcp = FastMCP("vision-smoke")
    register_tools(mcp, settings)
    img = _table_image()

    r1 = await mcp.call_tool(
        "analyze_image", {"image": img, "prompt": "用一句话描述这张图"}
    )
    print("ANALYZE:", _text(r1))

    r2 = await mcp.call_tool("ocr_image", {"image": img})
    print("OCR:", _text(r2))

    r3 = await mcp.call_tool("table_from_image", {"image": img})
    print("TABLE:", _text(r3))


if __name__ == "__main__":
    asyncio.run(run())
