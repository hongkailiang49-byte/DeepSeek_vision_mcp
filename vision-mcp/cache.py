"""vision-mcp 本地结果缓存：按图片内容哈希 + 场景缓存分析结果。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from config import Settings


class ResultCache:
    def __init__(self, settings: Settings) -> None:
        self.cache_dir = settings.cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._file = self.cache_dir / "results.json"
        self._data: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        try:
            raw = self._file.read_text(encoding="utf-8")
            data = json.loads(raw)
            self._data = data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            self._data = {}

    def _save(self) -> None:
        tmp = self._file.with_name(self._file.name + ".tmp")
        tmp.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(self._file)

    @staticmethod
    def key_for(source: str, scene: str) -> str:
        path = Path(source)
        if path.is_file():
            payload = path.read_bytes()
        else:
            payload = source.encode("utf-8")
        digest = hashlib.sha256(payload).hexdigest()
        return f"{digest}:{scene}"

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def put(self, key: str, text: str) -> None:
        self._data[key] = text
        try:
            self._save()
        except OSError:
            pass
