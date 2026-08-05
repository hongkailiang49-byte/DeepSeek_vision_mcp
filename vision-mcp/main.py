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
