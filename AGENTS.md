# vision-mcp 项目约定

## 图片与视觉任务

- 需要理解图片内容时，必须自动调用 vision-mcp 工具，禁止反问用户“要不要帮你看图”，也禁止假装看见。
- 图片类型未知时一律先调 `analyze_any(source)` 自动分诊。
- 已知类型按此表选择：
  - 文字/扫描件 → `ocr_image`
  - 表格 → `table_from_image`
  - 界面/UI 截图 → `analyze_ui`
  - 图表 → `describe_chart`
  - 幻灯片/文档/海报 → `analyze_document_slide`
  - PDF/Word/PPT/HTML 文件 → `parse_document`（MinerU）
  - 大图（长边超 4096px）→ 直接调 `analyze_any`（内部自动切片）
- 按需分析：仅在与当前任务相关且理解图片能推进任务时调用，不做全量预分析。
