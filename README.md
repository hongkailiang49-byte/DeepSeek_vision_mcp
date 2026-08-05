# vision-mcp

给 Codex / Claude Code / Cursor 等 MCP 客户端使用的视觉识别服务。默认调用智谱 GLM-4V-Flash（免费），支持任意 OpenAI 兼容后端与 Gemini。

项目主体代码位于 `vision-mcp/` 目录。

## 功能

- `analyze_image` 通用识图
- `image_info` 图片基本信息（本地计算，零成本）
- `ocr_image` 图片文字提取
- `table_from_image` 表格转 Markdown / Excel
- `analyze_ui` UI 截图分析（组件树 / 设计 token / 还原建议）
- `analyze_document_slide` 幻灯片 / 文档 / 海报分析
- `describe_chart` 图表解读
- `compare_images` 双图对比
- `tile_image` 大图切片逐块分析

## 安装

```bash
cd vision-mcp
python -m pip install -r requirements.txt
copy .env.example .env
```

编辑 `.env`，填入 `ZHIPU_API_KEY`（智谱开放平台 https://open.bigmodel.cn 免费获取，模型 `glm-4v-flash` 免费）。

## 接入 Codex

在 `~/.codex/config.toml` 添加：

```toml
[mcp_servers.vision-mcp]
command = "python"
args = ["D:/XingKe_Total_Work/codex视觉识别/vision-mcp/main.py"]
startup_timeout_sec = 60
```

如果 `python` 不在 PATH，换成 `py` 或完整 Python 路径。

## 切换后端

- OpenAI 兼容：设置 `VISION_API_BASE` / `VISION_API_KEY` / `VISION_MODEL`
- Gemini：`VISION_PROVIDER=gemini` + `VISION_API_KEY=AIza...`
- 本地 Ollama：`VISION_API_BASE=http://localhost:11434/v1`、`VISION_API_KEY=ollama`、`VISION_MODEL=llava`
- 无 key 调试：`VISION_MOCK=1`

## 常见问题

- 大图被压缩？检查 `VISION_AUTO_TILE` 与 `VISION_MAX_DIM`。
- 图片过大被拒？调高 `VISION_MAX_PIXELS`。
- 请求超时？调高 `VISION_TIMEOUT_MS`。
