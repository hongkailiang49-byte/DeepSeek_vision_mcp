import os

from config import Settings, load_settings


def test_load_settings_uses_defaults(monkeypatch, tmp_path):
    for name in list(os.environ):
        if (
            name.startswith("VISION_")
            or name.startswith("MINERU_")
            or name in {"ZHIPU_API_KEY", "GEMINI_API_KEY"}
        ):
            monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text("# empty\n", encoding="utf-8")
    settings = load_settings(env)
    assert settings.model == "glm-4.6v-flash"
    assert settings.provider == "auto"
    assert settings.auto_tile is True
    assert settings.timeout_ms == 60_000
    assert settings.proxy == ""
    assert settings.gemini_api_key == ""
    assert settings.mineru_api_key == ""
    assert settings.mineru_api_base == "https://mineru.net/api/v4"
    assert settings.mineru_model_version == "vlm"
    assert settings.mineru_max_wait_s == 600


def test_load_settings_reads_env_file(monkeypatch, tmp_path):
    for name in list(os.environ):
        if (
            name.startswith("VISION_")
            or name.startswith("MINERU_")
            or name in {"ZHIPU_API_KEY", "GEMINI_API_KEY"}
        ):
            monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "ZHIPU_API_KEY=sk-test\n"
        "VISION_MODEL=glm-4.6v-flash\n"
        "VISION_AUTO_TILE=0\n"
        "VISION_TIMEOUT_MS=30000\n",
        encoding="utf-8",
    )
    settings = load_settings(env)
    assert settings.zhipu_api_key == "sk-test"
    assert settings.auto_tile is False
    assert settings.timeout_ms == 30_000


def test_load_settings_reads_mineru_gemini_proxy(monkeypatch, tmp_path):
    for name in list(os.environ):
        if (
            name.startswith("VISION_")
            or name.startswith("MINERU_")
            or name in {"ZHIPU_API_KEY", "GEMINI_API_KEY"}
        ):
            monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "MINERU_API_KEY=sk-mineru\n"
        "MINERU_MODEL_VERSION=pipeline\n"
        "MINERU_MAX_WAIT_S=120\n"
        "GEMINI_API_KEY=gem-key\n"
        "VISION_PROXY=http://127.0.0.1:7897\n",
        encoding="utf-8",
    )
    settings = load_settings(env)
    assert settings.mineru_api_key == "sk-mineru"
    assert settings.mineru_model_version == "pipeline"
    assert settings.mineru_max_wait_s == 120
    assert settings.gemini_api_key == "gem-key"
    assert settings.proxy == "http://127.0.0.1:7897"


def test_env_overrides_dotenv(monkeypatch, tmp_path):
    monkeypatch.setenv("VISION_MODEL", "qwen-vl-plus")
    env = tmp_path / ".env"
    env.write_text("VISION_MODEL=glm-4.6v-flash\n", encoding="utf-8")
    settings = load_settings(env)
    assert settings.model == "qwen-vl-plus"


def test_cache_dir_default(monkeypatch, tmp_path):
    for name in list(os.environ):
        if (
            name.startswith("VISION_")
            or name.startswith("MINERU_")
            or name in {"ZHIPU_API_KEY", "GEMINI_API_KEY"}
        ):
            monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text("# empty\n", encoding="utf-8")
    settings = load_settings(env)
    assert settings.cache_dir.name == ".cache"
    assert settings.cache_dir.is_absolute()


def test_cache_dir_from_env(monkeypatch, tmp_path):
    for name in list(os.environ):
        if (
            name.startswith("VISION_")
            or name.startswith("MINERU_")
            or name in {"ZHIPU_API_KEY", "GEMINI_API_KEY"}
        ):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VISION_CACHE_DIR", str(tmp_path / "mycache"))
    env = tmp_path / ".env"
    env.write_text("# empty\n", encoding="utf-8")
    settings = load_settings(env)
    assert settings.cache_dir == tmp_path / "mycache"
