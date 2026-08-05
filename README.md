# vision-mcp

给 Codex / Claude Code / Cursor 等 MCP 客户端使用的视觉识别服务。默认调用智谱 GLM-4V-Flash（免费），支持任意 OpenAI 兼容后端、Gemini，以及 MinerU 文档解析。

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
- `parse_document` 用 MinerU 把 PDF/Word/PPT/图片/HTML 解析为 Markdown
- `parse_document_status` 查询 MinerU 解析任务状态
- `analyze_any` 自动分诊：判断图片类型（UI/表格/OCR/图表/文档/海报/通用）后按场景分析，带结果缓存
- `scan_folder` 扫描目录新增图片并自动分析（可配合定时自动化）

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
- Gemini：`VISION_PROVIDER=gemini` + `GEMINI_API_KEY=...`（或 `VISION_API_KEY`）；如网络受限，设置 `VISION_PROXY=http://127.0.0.1:7897`（本地代理端口按需修改）
- 本地 Ollama：`VISION_API_BASE=http://localhost:11434/v1`、`VISION_API_KEY=ollama`、`VISION_MODEL=llava`
- 无 key 调试：`VISION_MOCK=1`

## 自动识别

在 cc-switch 的 Prompts 面板启用“视觉自动识别”Codex 预设（写入 `~/.codex/AGENTS.md`）后，Codex 遇到与任务相关的图片会自动调用视觉工具，无需手动指定。规则：按需分析（相关才调用）、禁止反问、禁止虚构图片内容。

## MinerU 文档解析

`parse_document` 使用 [MinerU 精准解析 API](https://mineru.net/apiManage/docs)（需在 MinerU 官网申请 Token），支持 PDF、Word、PPT、图片和 HTML，输出 Markdown（表格、公式、OCR），可保存到本地。

```env
MINERU_API_KEY=你的token
MINERU_MODEL_VERSION=vlm   # pipeline | vlm | MinerU-HTML
MINERU_MAX_WAIT_S=600
```

- `source` 传本地路径或 URL 均可；本地文件会自动上传，URL 走服务端直传。
- 解析较慢时会轮询等待（默认 600 秒）；如果超时返回 `pending`，可拿 `task_id`/`batch_id` 调 `parse_document_status` 继续查询。
- HTML 文件请把 `model_version` 设为 `MinerU-HTML`；扫描件建议开启 `is_ocr`。

## 常见问题

- 大图被压缩？检查 `VISION_AUTO_TILE` 与 `VISION_MAX_DIM`。
- 图片过大被拒？调高 `VISION_MAX_PIXELS`。
- 请求超时？调高 `VISION_TIMEOUT_MS`。
