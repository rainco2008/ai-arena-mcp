# 内容工厂 n8n + MCP 实施方案

## 目标

本项目把 n8n 作为内容工厂编排层，把 SQLite 作为 MVP 数据库，把本项目的搜索/抓取/问答能力作为研究工具。当前本地实施目标是跑通：

```text
选题发现 -> 素材研究 -> 初稿生成 -> 质量检查 -> 人工审批路由 -> 发布 -> 指标回流
```

后期数据量、并发和多用户协作上来后，再把 SQLite 切换到 Postgres。

## 已落地组件

- 本地 n8n：`http://127.0.0.1:5678`
- SQLite 数据库：`data/content_factory.sqlite`
- 业务 CLI：`content_factory/cli.py`，n8n workflow 通过 `scripts/run_content_factory_task.cmd` 调用
- n8n workflow JSON：`workflows/n8n/content-factory-*.json`
- workflow 导入脚本：`scripts/import_content_factory_workflows.ps1`
- 端到端验证脚本：`scripts/verify_content_factory_e2e.ps1`
- MarkItDown 文档摄取：把 `data/inbox` 下的 PDF/DOCX/PPTX/XLSX/HTML/Markdown 等文件转换为 Markdown 并写入 `research_assets`

## 数据模型

SQLite 当前包含 6 类业务表：

- `topic_pool`：选题池与状态机。
- `research_assets`：研究素材、摘要、原文和来源可靠性。
- `content_items`：大纲、初稿、终稿、SEO 标题和发布状态。
- `review_records`：自动质检和人工审批记录。
- `publication_records`：发布渠道、URL、响应体和发布时间。
- `performance_metrics`：曝光、点击、转化、互动和平台原始指标。

表名、字段名和状态枚举尽量保持 Postgres 兼容。JSON 字段在 SQLite 中先用 `TEXT` 保存，迁移到 Postgres 后可切为 `JSONB`。

## 本地运行

初始化数据库：

```powershell
.\scripts\init_content_factory_db.ps1
```

启动 n8n：

```powershell
.\scripts\run_n8n.cmd
```

导入 workflow：

```powershell
.\scripts\import_content_factory_workflows.ps1
```

跑端到端验证：

```powershell
.\scripts\verify_content_factory_e2e.ps1
```

## 发布接口

`publish` 命令支持两种模式：

- 配置 `CONTENT_FACTORY_PUBLISH_WEBHOOK` 或传入 `--publish-webhook` 时，向目标 webhook POST 发布 payload。
- 未配置 webhook 时，默认写入 `manual://<channel>/<content_id>` 占位 URL，保证本地 MVP 可以完整跑通。

Webhook payload：

```json
{
  "content_id": "uuid",
  "topic_id": "uuid",
  "channel": "blog",
  "title": "SEO title",
  "meta_description": "description",
  "body": "final content"
}
```

Webhook 响应可返回 `url`、`link`、`permalink` 或 `id`，系统会记录到 `publication_records.url`。

## 文档摄取

本项目集成 Microsoft MarkItDown，用于把非网页资料转换成适合 LLM 使用的 Markdown。默认安全边界是只允许读取 `data/inbox` 下的文件，避免 n8n 或外部输入任意读取系统路径。

示例：

```powershell
scripts\run_content_factory_task.cmd seed-topic "whitepaper research" --priority 100
scripts\run_content_factory_task.cmd ingest-document --topic-id <topic-id> --file data\inbox\sample.md
```

摄取结果会写入：

- `research_assets.url`：本地文件 URL
- `research_assets.title`：文件名或传入标题
- `research_assets.summary`：Markdown 前 4000 字符
- `research_assets.raw_text`：完整 Markdown

n8n workflow：

```text
workflows/n8n/content-factory-document-ingestion.json
```

`Zie619/n8n-workflows` 已作为本地模板源集成到 `vendor/n8n-workflows`。它用于检索和参考，不直接作为运行时依赖，也不自动导入生产 n8n。

生成模板索引：

```powershell
npm run n8n:index-templates
```

搜索模板：

```powershell
.\scripts\index_n8n_workflow_templates.cmd --query "webhook slack approval" --limit 5
```

如果 PowerShell 拦截 `npm.ps1`，使用 `npm.cmd run n8n:index-templates`。

索引输出位于：

```text
workflows/template-index/zie619-n8n-workflows.index.json
```

## Postgres 迁移原则

- 保持现有表名、字段名、状态值不变。
- `TEXT` JSON 字段迁移为 `JSONB`。
- 时间字段迁移为 `timestamptz`。
- 先备份 SQLite，再冷迁移或短期双写。
- n8n credentials 和 workflow 数据库节点切换完成后，跑一次 dry-run 对比各表数量和最新内容状态。

## 风险控制

- 发布必须依赖 `review_records.decision = approve`。
- 素材中离线占位内容发布前必须人工替换或复核。
- workflow 默认不自动激活，导入后先人工检查 credential、路径和 webhook。
- 发布响应写入 `publication_records`，指标回流写入 `performance_metrics`，保证可追溯。
