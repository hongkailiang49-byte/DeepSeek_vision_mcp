"""场景提示词模板。"""
from __future__ import annotations

SCENES = {
    "general",
    "ui",
    "table",
    "slide",
    "document",
    "poster",
    "chart",
    "ocr",
    "compare",
}

_TEMPLATES: dict[str, str] = {
    "general": "请详细描述这张图片的内容，包括主体、场景、文字、颜色与风格。",
    "ocr": "请提取图片中的全部文字，按从左到右、从上到下的顺序输出文本块；"
    "不要漏掉小字，不要编造不存在的文字。",
    "table": "请把图片中的表格完整转换为 Markdown 表格，保留表头和所有行列，"
    "不要改动任何数值；如存在合并单元格请用注释说明。",
    "ui": "请分析这个 UI 截图：1) 组件树（缩进列表）；2) 布局结构；"
    "3) 设计 token（颜色/字体/间距）；4) 可落地的前端还原建议。",
    "slide": "请分析这一页幻灯片/文档：1) 标题；2) 要点列表；"
    "3) 图表或图片清单；4) 配色与排版风格；5) 输出 Markdown 大纲。",
    "document": "请分析这个文档页面：提取标题、段落结构、列表、表格和图片说明。",
    "poster": "请分析这张海报：主题、视觉风格、颜色、字体、构图、内含文字。",
    "chart": "请解读这个图表：图表类型、关键数据点、趋势、异常，并给出一句话结论。",
    "compare": "请对比两张图片，列出差异（结构/样式/内容），按严重程度排序。",
}


def template_for(scene: str) -> str:
    scene = scene.strip().lower()
    if scene not in SCENES:
        raise ValueError(f"未知场景：{scene}，可选：{', '.join(sorted(SCENES))}")
    return _TEMPLATES[scene]


def build_prompt(scene: str, user_prompt: str = "") -> str:
    base = template_for(scene)
    if user_prompt.strip():
        return f"{base}\n\n补充要求：{user_prompt.strip()}"
    return base
