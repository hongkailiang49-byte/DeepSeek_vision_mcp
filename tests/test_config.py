import os

from config import Settings, load_settings


def test_load_settings_uses_defaults(monkeypatch, tmp_path):
    for name in list(os.environ):
        if name.startswith("VISION_") or name == "ZHIPU_API_KEY":
            monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text("# empty\n", encoding="utf-8")
    settings = load_settings(env)
    assert settings.model == "glm-4v-flash"
    assert settings.provider == "auto"
    assert settings.auto_tile is True
    assert settings.timeout_ms == 60_000


def test_load_settings_reads_env_file(monkeypatch, tmp_path):
    for name in list(os.environ):
        if name.startswith("VISION_") or name == "ZHIPU_API_KEY":
            monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "ZHIPU_API_KEY=sk-test\n"
        "VISION_MODEL=glm-4v-flash\n"
        "VISION_AUTO_TILE=0\n"
        "VISION_TIMEOUT_MS=30000\n",
        encoding="utf-8",
    )
    settings = load_settings(env)
    assert settings.zhipu_api_key == "sk-test"
    assert settings.auto_tile is False
    assert settings.timeout_ms == 30_000


def test_env_overrides_dotenv(monkeypatch, tmp_path):
    monkeypatch.setenv("VISION_MODEL", "qwen-vl-plus")
    env = tmp_path / ".env"
    env.write_text("VISION_MODEL=glm-4v-flash\n", encoding="utf-8")
    settings = load_settings(env)
    assert settings.model == "qwen-vl-plus"
