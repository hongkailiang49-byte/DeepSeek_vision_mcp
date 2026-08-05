from config import Settings
from cache import ResultCache


def test_put_get_roundtrip(tmp_path):
    cache = ResultCache(Settings(cache_dir=tmp_path / "cache"))
    cache.put("k1", "hello")
    reloaded = ResultCache(Settings(cache_dir=tmp_path / "cache"))
    assert reloaded.get("k1") == "hello"


def test_missing_key_returns_none(tmp_path):
    cache = ResultCache(Settings(cache_dir=tmp_path / "cache"))
    assert cache.get("nope") is None


def test_corrupt_cache_resets(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "results.json").write_text("{broken", encoding="utf-8")
    cache = ResultCache(Settings(cache_dir=cache_dir))
    assert cache.get("k") is None
    cache.put("k", "v")
    assert ResultCache(Settings(cache_dir=cache_dir)).get("k") == "v"


def test_key_for_local_file_content(tmp_path):
    f = tmp_path / "a.png"
    f.write_bytes(b"aaa")
    k1 = ResultCache.key_for(str(f), "general")
    f.write_bytes(b"bbb")
    k2 = ResultCache.key_for(str(f), "general")
    assert k1 != k2


def test_key_for_url_stable():
    assert ResultCache.key_for("https://x/a.png", "ui") == ResultCache.key_for(
        "https://x/a.png", "ui"
    )
    assert ResultCache.key_for("https://x/a.png", "ui") != ResultCache.key_for(
        "https://x/a.png", "table"
    )
