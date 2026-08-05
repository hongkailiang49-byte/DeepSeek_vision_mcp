"""MinerU 文档解析客户端：PDF / Office / 图片 / HTML → Markdown。"""
from __future__ import annotations

import asyncio
import io
import time
import zipfile
from pathlib import Path

import httpx

from config import Settings
from providers import async_client_kwargs


class MinerUError(Exception):
    """面向用户的 MinerU 错误。"""


class MinerUClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = settings.mineru_api_base.rstrip("/")
        self.api_key = settings.mineru_api_key

    def _headers(self, json_body: bool = True) -> dict[str, str]:
        if not self.api_key:
            raise MinerUError("缺少 MinerU API key，请在 .env 设置 MINERU_API_KEY")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(**async_client_kwargs(self.settings))

    def _parse(self, resp: httpx.Response, what: str) -> dict:
        if resp.status_code >= 400:
            raise MinerUError(f"MinerU {what} 返回 {resp.status_code}：{resp.text[:300]}")
        try:
            body = resp.json()
        except ValueError as exc:
            raise MinerUError(f"MinerU {what} 返回非 JSON 响应") from exc
        if body.get("code") != 0:
            raise MinerUError(f"MinerU {what} 失败：{body.get('msg') or body}")
        return body.get("data") or {}

    def _options(
        self,
        model_version: str,
        is_ocr: bool,
        enable_table: bool,
        enable_formula: bool,
        language: str,
        page_ranges: str,
        data_id: str,
    ) -> dict:
        payload = {
            "model_version": model_version or self.settings.mineru_model_version,
            "is_ocr": is_ocr,
            "enable_table": enable_table,
            "enable_formula": enable_formula,
            "language": language,
        }
        if page_ranges:
            payload["page_ranges"] = page_ranges
        if data_id:
            payload["data_id"] = data_id
        return payload

    async def submit_url(
        self,
        url: str,
        *,
        model_version: str = "",
        is_ocr: bool = False,
        enable_table: bool = True,
        enable_formula: bool = True,
        language: str = "ch",
        page_ranges: str = "",
        data_id: str = "",
    ) -> str:
        payload = {"url": url}
        payload.update(
            self._options(
                model_version, is_ocr, enable_table, enable_formula,
                language, page_ranges, data_id,
            )
        )
        async with self._client() as client:
            resp = await client.post(
                f"{self.base_url}/extract/task", headers=self._headers(), json=payload
            )
            data = self._parse(resp, "创建任务")
        return data["task_id"]

    async def submit_local(
        self,
        path: str,
        *,
        model_version: str = "",
        is_ocr: bool = False,
        enable_table: bool = True,
        enable_formula: bool = True,
        language: str = "ch",
        page_ranges: str = "",
        data_id: str = "",
    ) -> str:
        file_path = Path(path)
        if not file_path.is_file():
            raise MinerUError(f"文件不存在：{file_path}")
        file_info: dict = {"name": file_path.name}
        if data_id:
            file_info["data_id"] = data_id
        if page_ranges:
            file_info["page_ranges"] = page_ranges
        payload = {"files": [file_info]}
        payload.update(
            self._options(
                model_version, is_ocr, enable_table, enable_formula,
                language, "", "",
            )
        )
        async with self._client() as client:
            resp = await client.post(
                f"{self.base_url}/file-urls/batch",
                headers=self._headers(),
                json=payload,
            )
            data = self._parse(resp, "申请上传链接")
        batch_id = data["batch_id"]
        content = file_path.read_bytes()
        async with self._client() as client:
            for upload_url in data.get("file_urls", []):
                up_resp = await client.put(upload_url, content=content)
                if up_resp.status_code >= 400:
                    raise MinerUError(
                        f"文件上传失败 {up_resp.status_code}：{up_resp.text[:200]}"
                    )
        return batch_id

    async def task_status(self, task_id: str) -> dict:
        async with self._client() as client:
            resp = await client.get(
                f"{self.base_url}/extract/task/{task_id}",
                headers=self._headers(json_body=False),
            )
            return self._parse(resp, "查询任务")

    async def batch_status(self, batch_id: str) -> list[dict]:
        async with self._client() as client:
            resp = await client.get(
                f"{self.base_url}/extract-results/batch/{batch_id}",
                headers=self._headers(json_body=False),
            )
            data = self._parse(resp, "查询批量任务")
        return data.get("extract_result") or []

    async def wait_task(
        self,
        task_id: str,
        *,
        max_wait_s: int | None = None,
        poll_interval_s: float = 5.0,
    ) -> dict:
        deadline = time.monotonic() + (
            max_wait_s if max_wait_s is not None else self.settings.mineru_max_wait_s
        )
        while True:
            data = await self.task_status(task_id)
            state = data.get("state")
            if state == "done":
                return data
            if state == "failed":
                raise MinerUError(data.get("err_msg") or "MinerU 解析失败")
            if time.monotonic() >= deadline:
                raise MinerUError("MinerU 解析超时")
            await asyncio.sleep(poll_interval_s)

    async def wait_batch(
        self,
        batch_id: str,
        *,
        max_wait_s: int | None = None,
        poll_interval_s: float = 5.0,
    ) -> list[dict]:
        deadline = time.monotonic() + (
            max_wait_s if max_wait_s is not None else self.settings.mineru_max_wait_s
        )
        while True:
            results = await self.batch_status(batch_id)
            failed = [r for r in results if r.get("state") == "failed"]
            if failed:
                raise MinerUError(failed[0].get("err_msg") or "MinerU 批量解析失败")
            if results and all(r.get("state") == "done" for r in results):
                return results
            if time.monotonic() >= deadline:
                raise MinerUError("MinerU 解析超时")
            await asyncio.sleep(poll_interval_s)

    async def download_markdown(
        self, zip_url: str, out_dir: Path | None = None
    ) -> tuple[str, str]:
        async with self._client() as client:
            resp = await client.get(zip_url)
            if resp.status_code >= 400:
                raise MinerUError(
                    f"下载解析结果失败：{resp.status_code} {resp.text[:200]}"
                )
            content = resp.content
        try:
            zf = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile as exc:
            raise MinerUError("MinerU 结果压缩包无效") from exc
        names = [name for name in zf.namelist() if name.endswith("full.md")]
        if not names:
            raise MinerUError(f"结果压缩包中没有 full.md：{zf.namelist()}")
        text = zf.read(names[0]).decode("utf-8", errors="replace")
        out = out_dir or self.settings.output_dir
        out.mkdir(parents=True, exist_ok=True)
        md_path = out / "full.md"
        md_path.write_text(text, encoding="utf-8")
        return text, str(md_path)

    async def status(self, task_id: str = "", batch_id: str = "") -> dict:
        if task_id:
            return {"task_id": task_id, **await self.task_status(task_id)}
        if batch_id:
            results = await self.batch_status(batch_id)
            states = [r.get("state", "?") for r in results]
            return {
                "batch_id": batch_id,
                "state": states[0] if len(states) == 1 else ",".join(states),
                "items": results,
            }
        raise MinerUError("请提供 task_id 或 batch_id")

    async def parse(
        self,
        source: str,
        *,
        out_dir: Path | None = None,
        save_md: bool = True,
        max_wait_s: int = 0,
        poll_interval_s: float = 5.0,
        **options,
    ) -> dict:
        if source.startswith(("http://", "https://")):
            task_id = await self.submit_url(source, **options)
            batch_id = ""
        else:
            task_id = ""
            batch_id = await self.submit_local(source, **options)

        if max_wait_s == 0:
            return {
                "state": "pending",
                "task_id": task_id,
                "batch_id": batch_id,
                "message": "已提交 MinerU 解析任务，可稍后调用 parse_document_status 查询。",
            }

        wait = max_wait_s if max_wait_s > 0 else self.settings.mineru_max_wait_s
        try:
            if task_id:
                data = await self.wait_task(
                    task_id, max_wait_s=wait, poll_interval_s=poll_interval_s
                )
            else:
                results = await self.wait_batch(
                    batch_id, max_wait_s=wait, poll_interval_s=poll_interval_s
                )
                data = results[0]
        except MinerUError as exc:
            if "超时" in str(exc):
                return {
                    "state": "pending",
                    "task_id": task_id,
                    "batch_id": batch_id,
                    "message": (
                        "任务仍在排队或解析中，可稍后调用 parse_document_status "
                        "查询（传入 task_id 或 batch_id）。"
                    ),
                }
            raise

        text, md_path = await self.download_markdown(
            data["full_zip_url"], out_dir=out_dir
        )
        return {
            "state": "done",
            "source": source,
            "task_id": task_id,
            "batch_id": batch_id,
            "full_zip_url": data.get("full_zip_url", ""),
            "markdown": text,
            "md_path": md_path if save_md else "",
        }
