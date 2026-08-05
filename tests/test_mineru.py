import asyncio
import io
import json
import zipfile

from config import Settings
from mineru import MinerUClient, MinerUError


class FakeResponse:
    def __init__(self, status_code=200, data=None, content=b""):
        self.status_code = status_code
        self._data = data
        self.content = content

    @property
    def text(self):
        if self._data is None:
            return ""
        return json.dumps(self._data, ensure_ascii=False)

    def json(self):
        return self._data


class FakeClient:
    def __init__(self, responses, **init_kwargs):
        self.responses = list(responses)
        self.init_kwargs = init_kwargs
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def _next(self):
        if not self.responses:
            raise AssertionError("no fake response left")
        return self.responses.pop(0)

    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self._next()

    async def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self._next()

    async def put(self, url, **kwargs):
        self.calls.append(("PUT", url, kwargs))
        return self._next()


def _make_client(monkeypatch, responses, settings=None):
    client = FakeClient(responses)
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: client)
    return client, MinerUClient(
        settings or Settings(mineru_api_key="sk-mineru", timeout_ms=5000)
    )


def _zip_with_full_md(text="hello markdown"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("full.md", text)
    return buf.getvalue()


async def _no_sleep(*args, **kwargs):
    return None


def test_submit_url_returns_task_id(monkeypatch):
    fake, client = _make_client(
        monkeypatch,
        [FakeResponse(200, {"code": 0, "data": {"task_id": "t1"}, "msg": "ok"})],
    )

    async def run():
        return await client.submit_url(
            "https://example.com/a.pdf", is_ocr=True, enable_table=True
        )

    assert asyncio.run(run()) == "t1"
    method, url, kwargs = fake.calls[0]
    assert method == "POST"
    assert url.endswith("/extract/task")
    assert kwargs["headers"]["Authorization"] == "Bearer sk-mineru"
    assert kwargs["json"]["url"] == "https://example.com/a.pdf"
    assert kwargs["json"]["model_version"] == "vlm"
    assert kwargs["json"]["is_ocr"] is True


def test_submit_local_uploads_and_returns_batch_id(monkeypatch, tmp_path):
    local = tmp_path / "demo.pdf"
    local.write_bytes(b"%PDF-demo")
    fake, client = _make_client(
        monkeypatch,
        [
            FakeResponse(
                200,
                {
                    "code": 0,
                    "data": {
                        "batch_id": "b1",
                        "file_urls": ["https://upload.example/x.pdf"],
                    },
                    "msg": "ok",
                },
            ),
            FakeResponse(200),
        ],
    )

    async def run():
        return await client.submit_local(str(local))

    assert asyncio.run(run()) == "b1"
    assert fake.calls[0][0] == "POST"
    assert fake.calls[0][1].endswith("/file-urls/batch")
    assert fake.calls[0][2]["json"]["files"] == [{"name": "demo.pdf"}]
    assert fake.calls[1][0] == "PUT"
    assert fake.calls[1][1] == "https://upload.example/x.pdf"
    assert fake.calls[1][2]["content"] == b"%PDF-demo"


def test_wait_task_polls_until_done(monkeypatch):
    fake, client = _make_client(
        monkeypatch,
        [
            FakeResponse(200, {"code": 0, "data": {"state": "pending"}, "msg": "ok"}),
            FakeResponse(
                200,
                {
                    "code": 0,
                    "data": {"state": "done", "full_zip_url": "https://z/full.zip"},
                    "msg": "ok",
                },
            ),
        ],
    )
    monkeypatch.setattr("asyncio.sleep", _no_sleep)

    async def run():
        return await client.wait_task("t1", max_wait_s=30, poll_interval_s=0.01)

    result = asyncio.run(run())
    assert result["state"] == "done"
    assert result["full_zip_url"] == "https://z/full.zip"
    assert [c[0] for c in fake.calls] == ["GET", "GET"]
    assert fake.calls[0][1].endswith("/extract/task/t1")


def test_wait_task_raises_on_failed(monkeypatch):
    _, client = _make_client(
        monkeypatch,
        [
            FakeResponse(
                200,
                {
                    "code": 0,
                    "data": {"state": "failed", "err_msg": "文件格式不支持"},
                    "msg": "ok",
                },
            )
        ],
    )

    async def run():
        return await client.wait_task("t1", max_wait_s=30, poll_interval_s=0.01)

    try:
        asyncio.run(run())
        raise AssertionError("should have raised")
    except MinerUError as exc:
        assert "文件格式不支持" in str(exc)


def test_download_markdown_extracts_full_md(monkeypatch, tmp_path):
    fake, client = _make_client(
        monkeypatch,
        [FakeResponse(200, content=_zip_with_full_md("hello markdown"))],
    )

    async def run():
        return await client.download_markdown("https://z/full.zip", out_dir=tmp_path)

    text, md_path = asyncio.run(run())
    assert text == "hello markdown"
    assert md_path == str(tmp_path / "full.md")
    assert (tmp_path / "full.md").read_text(encoding="utf-8") == "hello markdown"
    assert fake.calls[0][0] == "GET"


def test_parse_url_waits_and_returns_markdown(monkeypatch, tmp_path):
    fake, client = _make_client(
        monkeypatch,
        [
            FakeResponse(200, {"code": 0, "data": {"task_id": "t1"}, "msg": "ok"}),
            FakeResponse(
                200,
                {
                    "code": 0,
                    "data": {"state": "done", "full_zip_url": "https://z/full.zip"},
                    "msg": "ok",
                },
            ),
            FakeResponse(200, content=_zip_with_full_md("# 文档内容")),
        ],
    )
    monkeypatch.setattr("asyncio.sleep", _no_sleep)

    async def run():
        return await client.parse(
            "https://example.com/a.pdf", out_dir=tmp_path, max_wait_s=30
        )

    result = asyncio.run(run())
    assert result["state"] == "done"
    assert result["markdown"] == "# 文档内容"
    assert result["md_path"] == str(tmp_path / "full.md")
    assert (tmp_path / "full.md").is_file()


def test_parse_local_file_uses_batch_flow(monkeypatch, tmp_path):
    local = tmp_path / "demo.pdf"
    local.write_bytes(b"%PDF-demo")
    fake, client = _make_client(
        monkeypatch,
        [
            FakeResponse(
                200,
                {
                    "code": 0,
                    "data": {
                        "batch_id": "b1",
                        "file_urls": ["https://upload.example/x.pdf"],
                    },
                    "msg": "ok",
                },
            ),
            FakeResponse(200),
            FakeResponse(
                200,
                {
                    "code": 0,
                    "data": {
                        "extract_result": [
                            {
                                "file_name": "demo.pdf",
                                "state": "done",
                                "full_zip_url": "https://z/full.zip",
                            }
                        ]
                    },
                    "msg": "ok",
                },
            ),
            FakeResponse(200, content=_zip_with_full_md("本地文件解析结果")),
        ],
    )
    monkeypatch.setattr("asyncio.sleep", _no_sleep)

    async def run():
        return await client.parse(str(local), out_dir=tmp_path, max_wait_s=30)

    result = asyncio.run(run())
    assert result["state"] == "done"
    assert result["markdown"] == "本地文件解析结果"
    assert result["batch_id"] == "b1"
    assert [c[0] for c in fake.calls] == ["POST", "PUT", "GET", "GET"]


def test_parse_without_key_raises(monkeypatch):
    _, client = _make_client(monkeypatch, [], settings=Settings(timeout_ms=5000))

    async def run():
        return await client.submit_url("https://example.com/a.pdf")

    try:
        asyncio.run(run())
        raise AssertionError("should have raised")
    except MinerUError as exc:
        assert "MINERU_API_KEY" in str(exc)


def test_parse_returns_pending_when_wait_exceeds(monkeypatch):
    fake, client = _make_client(
        monkeypatch,
        [
            FakeResponse(200, {"code": 0, "data": {"task_id": "t1"}, "msg": "ok"}),
            FakeResponse(200, {"code": 0, "data": {"state": "pending"}, "msg": "ok"}),
        ],
    )

    async def run():
        return await client.parse(
            "https://example.com/a.pdf", max_wait_s=0, poll_interval_s=0.01
        )

    result = asyncio.run(run())
    assert result["state"] == "pending"
    assert result["task_id"] == "t1"
    assert "parse_document_status" in result["message"]
