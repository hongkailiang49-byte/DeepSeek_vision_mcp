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
    max_tokens: int = 1024
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
        max_tokens=_env_int("VISION_MAX_TOKENS", 1024),
        max_pixels=_env_int("VISION_MAX_PIXELS", 50_000_000),
        auto_tile=_env_bool("VISION_AUTO_TILE", True),
        tile_threshold=_env_int("VISION_AUTO_TILE_THRESHOLD", 4096),
        tile_size=_env_int("VISION_TILE_SIZE", 1536),
        tile_overlap=_env_int("VISION_TILE_OVERLAP", 64),
        max_dim=_env_int("VISION_MAX_DIM", 10_000),
        mock=_env_bool("VISION_MOCK", False),
        output_dir=out,
    )
