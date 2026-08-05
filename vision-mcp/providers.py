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
