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
    def __init__(self, responses, **init_kwargs):
        self.responses = responses
        self.init_kwargs = init_kwargs
        self.calls = 0
        self.last_kwargs = None

    def init(self, **kwargs):
        self.init_kwargs = kwargs
        return self

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


from providers import GeminiProvider, MockProvider, get_provider


def test_get_provider_mock():
    assert isinstance(get_provider(Settings(mock=True)), MockProvider)


def test_get_provider_gemini():
    assert isinstance(get_provider(Settings(provider="gemini", api_key="k")), GeminiProvider)


def test_get_provider_auto():
    assert isinstance(
        get_provider(Settings(provider="auto", api_key="k")),
        OpenAICompatibleProvider,
    )


def test_mock_complete():
    async def run():
        provider = MockProvider(Settings(mock=True))
        return await provider.complete("hi", [Image.new("RGB", (4, 4))])

    text = asyncio.run(run())
    assert "[mock]" in text
    assert "4x4" in text


def test_gemini_payload_flow(monkeypatch):
    ok = FakeResponse(
        200,
        data={"candidates": [{"content": {"parts": [{"text": "gemini ok"}]}}]},
    )
    client = FakeClient([ok])
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: client)

    async def run():
        provider = GeminiProvider(Settings(provider="gemini", api_key="k", timeout_ms=1000))
        return await provider.complete("hi", [Image.new("RGB", (4, 4))])

    assert asyncio.run(run()) == "gemini ok"
    assert client.last_kwargs["params"] == {"key": "k"}


def test_openai_provider_passes_proxy(monkeypatch):
    ok = FakeResponse(200, data={"choices": [{"message": {"content": "ok"}}]})
    client = FakeClient([ok])
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: client.init(**kw))

    async def run():
        provider = OpenAICompatibleProvider(
            Settings(api_key="k", timeout_ms=1000, proxy="http://127.0.0.1:7897")
        )
        return await provider.complete("hi", [Image.new("RGB", (4, 4))])

    assert asyncio.run(run()) == "ok"
    assert client.init_kwargs["proxy"] == "http://127.0.0.1:7897"


def test_gemini_provider_prefers_gemini_api_key(monkeypatch):
    ok = FakeResponse(
        200,
        data={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]},
    )
    client = FakeClient([ok])
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: client)

    async def run():
        provider = GeminiProvider(
            Settings(
                provider="gemini",
                gemini_api_key="gk",
                api_key="ak",
                zhipu_api_key="zk",
                timeout_ms=1000,
            )
        )
        return await provider.complete("hi", [Image.new("RGB", (4, 4))])

    assert asyncio.run(run()) == "ok"
    assert client.last_kwargs["params"] == {"key": "gk"}


def test_gemini_provider_passes_proxy(monkeypatch):
    ok = FakeResponse(
        200,
        data={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]},
    )
    client = FakeClient([ok])
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: client.init(**kw))

    async def run():
        provider = GeminiProvider(
            Settings(
                provider="gemini",
                api_key="k",
                timeout_ms=1000,
                proxy="http://127.0.0.1:7897",
            )
        )
        return await provider.complete("hi", [Image.new("RGB", (4, 4))])

    assert asyncio.run(run()) == "ok"
    assert client.init_kwargs["proxy"] == "http://127.0.0.1:7897"
