import asyncio

from PIL import Image

from config import Settings
from providers import OpenAICompatibleProvider, ProviderError


class FakeResponse:
    def __init__(self, status_code=200, text="", data=None):
        self.status_code = status_code
        self._text = text
        self._data = data

    @property
    def text(self):
        return self._text

    def json(self):
        return self._data


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = 0
        self.last_kwargs = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        return self.responses[min(self.calls - 1, len(self.responses) - 1)]


def test_payload_shape():
    settings = Settings(api_key="k", model="glm-4v-flash")
    provider = OpenAICompatibleProvider(settings)
    img = Image.new("RGB", (10, 10))
    payload = provider._payload("describe", [img])
    assert payload["model"] == "glm-4v-flash"
    assert payload["messages"][0]["content"][0] == {"type": "text", "text": "describe"}
    assert payload["messages"][0]["content"][1]["type"] == "image_url"
    assert payload["messages"][0]["content"][1]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )


def test_success_returns_content(monkeypatch):
    ok = FakeResponse(200, data={"choices": [{"message": {"content": "ok"}}]})
    client = FakeClient([ok])
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: client)

    async def run():
        provider = OpenAICompatibleProvider(Settings(api_key="k", timeout_ms=1000))
        return await provider.complete("hi", [Image.new("RGB", (4, 4))])

    assert asyncio.run(run()) == "ok"
    assert client.calls == 1


def test_retry_on_429_then_success(monkeypatch):
    ok = FakeResponse(200, data={"choices": [{"message": {"content": "ok"}}]})
    client = FakeClient([FakeResponse(429, text="slow"), ok])
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: client)

    async def run():
        provider = OpenAICompatibleProvider(Settings(api_key="k", timeout_ms=1000))
        return await provider.complete("hi", [Image.new("RGB", (4, 4))])

    assert asyncio.run(run()) == "ok"
    assert client.calls == 2


def test_failure_raises_provider_error(monkeypatch):
    bad = FakeResponse(401, text="unauthorized")
    client = FakeClient([bad])
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: client)

    async def run():
        provider = OpenAICompatibleProvider(Settings(api_key="k", timeout_ms=1000))
        return await provider.complete("hi", [Image.new("RGB", (4, 4))])

    try:
        asyncio.run(run())
        raise AssertionError("should have raised")
    except ProviderError as exc:
        assert "401" in str(exc)
