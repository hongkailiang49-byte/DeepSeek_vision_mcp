# Vision MCP 设计文档

- 日期：2026-08-05
- 状态：已评审，待实现
- 项目位置：`vision-mcp/`（工作区根目录下）

## 1. 背景与目标

给 Codex 提供一个自研的视觉识别 MCP，改善模型在以下场景的表现：

- 图片理解：识图、OCR、双图对比、图片基本信息
- 前端设计：UI 截图分析（组件树、布局、设计 token）、还原建议
- 表格：图片/截图转 Markdown 表格，可选导出 Excel
- PPT/文档：单页幻灯片结构分析、图表解读、Markdown 大纲

硬性约束：

1. 默认使用免费云端 API：智谱 GLM-4V-Flash（OpenAI 兼容，国内直连）。
2. 多后端可配置：OpenAI 兼容服务（智谱 / Qwen / Kimi / Ollama / LM Studio）以及 Gemini。
3. 尽量不受图片大小限制：大图自动切片，逐块分析后合并。
4. 代码完全自研，不 fork 第三方项目。

## 2. 范围

### v1 包含

9 个 MCP 工具，规格见第 5 节。

### v1 不包含

- 图像生成 / 编辑
- 屏幕控制 / computer use
- 视频分析
- Figma 直接集成（可由 Codex 结合 Figma MCP 实现）
- 网页自动截图（可由浏览器 MCP 配合）

## 3. 项目结构

```text
vision-mcp/
├── main.py              # MCP 入口：注册所有工具，stdio 启动，加载 .env
├── providers.py         # 视觉后端层：OpenAI 兼容 + Gemini + mock
├── image_utils.py       # 图片读取、格式转换、尺寸信息、防解压炸弹、大图切片
├── prompts.py           # 各场景提示词模板
├── tools.py             # 工具定义、参数校验、错误包装
├── requirements.txt     # mcp, pillow, httpx, openpyxl
├── .env.example         # 配置模板（不含真实 key）
├── .env                 # 本地密钥（gitignore，不提交）
├── .gitignore
├── README.md            # 安装 / 配置 / Codex 接入说明
└── output/              # 运行时导出目录（gitignore）
```

## 4. 架构与数据流

```text
Codex / MCP 客户端
        │  stdio (JSON-RPC)
        ▼
main.py ──► tools.py（9 个工具，参数校验，错误包装）
                │
                ├──► image_utils.py（加载/校验/切片）
                │
                ├──► prompts.py（按场景取提示词）
                │
                └──► providers.py（OpenAI 兼容 / Gemini / mock）
                           │
                           ▼
                    视觉模型 API（默认智谱 GLM-4V-Flash，免费）
```

一次工具调用的完整流程：

1. 工具收到图片来源：本地路径 / HTTP(S) URL / base64。
2. `image_utils` 加载并校验（格式、像素上限），返回宽高、格式、大小等本地信息。
3. 若图片长边超过阈值（默认 4096px）且 `VISION_AUTO_TILE=1`，按网格切片。
4. `providers` 把每张图转成 base64 data URL，构造请求发给视觉模型。
5. 返回文本结果；表格类工具额外返回 Markdown；OCR 返回文本块与坐标；必要时导出 `.xlsx`。

## 5. 工具规格

通用输入约定：`image` 参数支持本地绝对/相对路径、`http(s)://` URL、`data:image/...;base64,` 或裸 base64。

| 工具 | 参数 | 返回 |
|---|---|---|
| `analyze_image` | `image`, `prompt?`, `scene?` | 自然语言分析；`scene` 可选：general/ui/table/slide/chart |
| `image_info` | `image` | 宽高、格式、文件大小、颜色模式（纯本地，不调 API） |
| `ocr_image` | `image`, `language?` | 文本块列表：内容、置信度、bbox（相对像素坐标） |
| `table_from_image` | `image`, `export_xlsx?`, `out_path?` | Markdown 表格 + 行列数；可选导出 `.xlsx` |
| `analyze_ui` | `image`, `focus?` | 组件树摘要、布局结构、设计 token（颜色/字体/间距）、还原建议 |
| `analyze_document_slide` | `image`, `scene?` | 标题/要点/图表清单、配色排版、Markdown 大纲；`scene` 可选 slide/document/poster |
| `describe_chart` | `image`, `chart_type?` | 图表类型、数据点、趋势、异常与结论 |
| `compare_images` | `image_a`, `image_b`, `focus?` | 差异列表：结构/样式/内容，按严重程度排序 |
| `tile_image` | `image`, `tile_size?`, `prompt?` | 切片数、逐块分析结果合并后的综合结论 |

## 6. 视觉后端层

`providers.py` 实现三个后端类：

- `OpenAICompatibleProvider`：构造 `/chat/completions` 请求，图片以 `image_url` + base64 data URL 传入。覆盖智谱、Qwen、Kimi、Ollama、LM Studio。
- `GeminiProvider`：构造 Google `generativelanguage` REST 请求，图片以 `inline_data` 传入。
- `MockProvider`：`VISION_MOCK=1` 时返回示例结果，不联网，用于无 key 调试。

默认配置：

```text
base_url = https://open.bigmodel.cn/api/paas/v4/
model    = glm-4v-flash
api_key  = ZHIPU_API_KEY（来自 .env）
```

配置优先级：工具调用参数 > 环境变量 > 默认值。

## 7. 图片预处理

- 支持格式：PNG / JPEG / WebP / BMP / GIF（取首帧）。
- 不支持格式自动转 PNG 再发送。
- 解压炸弹防护：解码像素总数超过 `VISION_MAX_PIXELS`（默认 50MP）时拒绝。
- 自动切片：长边 > `VISION_AUTO_TILE_THRESHOLD`（默认 4096px）且开关开启时，按 `VISION_TILE_SIZE`（默认 1536px）网格切片，块间保留少量重叠（默认 64px），逐块请求后按编号合并结果。
- 超大图防护：切片前若长边超过 `VISION_MAX_DIM`（默认 10000px）先等比缩放；设为 0 可关闭。
- 所有预处理只影响发送给模型的副本，不修改原图。

## 8. 提示词模板

`prompts.py` 按场景提供模板：

- `general`：详细描述图片内容、主体、文字、风格。
- `ocr`：逐文本块输出，含 bbox 坐标；强调不要漏小字。
- `table`：输出完整 Markdown 表格，保留表头、行列对应、合并单元格说明；数值不做猜测。
- `ui`：输出组件树（缩进列表或 JSON）、布局结构、颜色/字体/间距 token、可实现的前端还原建议。
- `slide`：输出标题、要点列表、图表/图片清单、配色排版风格、Markdown 大纲。
- `chart`：输出图表类型、关键数据点、趋势、异常、一句话结论。
- `compare`：输出结构化差异列表（结构/样式/内容），按严重程度排序。

所有模板要求：中文输出、不确定处明确标注、不编造图片中不存在的内容。

## 9. 配置项（.env）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `ZHIPU_API_KEY` | 无 | 智谱 API key |
| `VISION_PROVIDER` | `auto` | `auto`/`openai`/`gemini`/`mock` |
| `VISION_API_BASE` | 智谱地址 | OpenAI 兼容服务地址 |
| `VISION_API_KEY` | 空 | 覆盖默认 key |
| `VISION_MODEL` | `glm-4v-flash` | 视觉模型名 |
| `VISION_TIMEOUT_MS` | `60000` | 单次请求超时 |
| `VISION_MAX_TOKENS` | `4096` | 输出上限 |
| `VISION_MAX_PIXELS` | `50000000` | 解压炸弹防护 |
| `VISION_AUTO_TILE` | `1` | 大图自动切片开关 |
| `VISION_AUTO_TILE_THRESHOLD` | `4096` | 触发切片的长边阈值 |
| `VISION_TILE_SIZE` | `1536` | 切片边长 |
| `VISION_TILE_OVERLAP` | `64` | 切片重叠像素 |
| `VISION_MAX_DIM` | `10000` | 切片前最大长边，0=关闭 |
| `VISION_MOCK` | `0` | 1 时启用 mock 后端 |
| `VISION_OUTPUT_DIR` | `./output` | Excel 等导出目录 |

## 10. 错误处理

- 输入错误（文件不存在、格式不支持、超过像素上限）：返回明确的中文错误信息。
- 网络 / 上游错误：超时 60s；429/5xx 重试 2 次，指数退避；仍失败返回可读信息。
- 模型返回截断或空内容：返回结果并附加 `warning` 说明。
- 所有错误统一包装为工具返回的文本内容，不让客户端看到裸异常或堆栈。

## 11. 安全

- API key 只存 `.env`，`.gitignore` 排除，不硬编码、不提交。
- URL 图片下载仅允许 `http/https`，做基础 SSRF 过滤：阻止私网、链路本地、以及云元数据地址（如 `169.254.169.254`）。
- 导出文件路径默认限制在 `VISION_OUTPUT_DIR` 内；用户显式指定其他路径时仅接受绝对路径。
- Mock 模式不产生任何网络请求。

## 12. 测试策略

三层测试：

1. 单元测试（`pytest`）：`image_utils`（加载/格式转换/像素上限/切片网格计算）、`providers`（请求构造，mock httpx）、`prompts`（模板包含必需占位符）。
2. Mock 联调：`VISION_MOCK=1` 启动 MCP，用客户端列出 9 个工具并各调用一次，验证协议与返回结构。
3. 真实联调：使用用户提供的智谱 key，合成测试图，实际跑 `analyze_image`、`ocr_image`、`table_from_image` 各一次，验证端到端。

验收标准：

- 9 个工具全部注册成功，mock 模式无 key 可运行。
- 真实 key 下三个核心工具端到端通过。
- 合成长截图验证自动切片路径可用。
- README 包含 Codex 接入配置（`~/.codex/config.toml` 示例）。

## 13. 交付与安装

- 交付：`vision-mcp/` 完整代码、README、`.env.example`、测试。
- 安装：README 提供 Codex 配置；可选帮用户写入 `~/.codex/config.toml`（先备份，用户确认后执行）。

## 14. 成功标准

- 在 Codex 中能通过 MCP 调用 9 个工具并获得结构化结果。
- 图片、前端、表格、PPT 四类场景各有一个可演示的工具调用示例。
- 大图切片路径真实有效，避免模型降采样丢细节。
