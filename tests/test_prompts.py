import pytest

from prompts import SCENES, build_prompt, template_for


def test_scene_set_has_required_scenes():
    assert {
        "general",
        "ui",
        "table",
        "slide",
        "document",
        "poster",
        "chart",
        "ocr",
        "compare",
    } <= SCENES


def test_template_for_all_scenes():
    for scene in SCENES:
        text = template_for(scene)
        assert text
        assert "图片" in text or "截图" in text or "图表" in text or "海报" in text


def test_template_contains_scene_specific_markers():
    assert "Markdown 表格" in template_for("table")
    assert "组件树" in template_for("ui")
    assert "图表类型" in template_for("chart")
    assert "差异" in template_for("compare")


def test_build_prompt_appends_user_prompt():
    text = build_prompt("table", "只要前 3 行")
    assert "补充要求：只要前 3 行" in text


def test_unknown_scene_raises():
    with pytest.raises(ValueError, match="未知场景"):
        template_for("nope")
