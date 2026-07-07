# ContentPilot

面向 SaaS 的管理控制台和资源数据库，用于配置网站内容获取、跟踪抓取进度、检查收集的元数据/结果，并控制下游清洗、发布和指标工作流。

ContentPilot 使用 Scrapling 作为默认的搜索/网页抓取执行层，并保留 CloakBrowser 作为可选的浏览器辅助抓取后端。MCP 和兼容 OpenAI 的 API 仍然可用作集成接口，但核心产品是管理控制台和资源数据库。

## 功能特性

- **资源获取管理控制台**：
  - 配置需要收集的网站域名。
  - 查看网站元数据、站点地图（Sitemap）、URL 队列、抓取运行记录、页面结果、摘要和嵌入向量（Embeddings）。
  - 从控制台启动获取、处理、发布和指标工作流。
- **内容/资源数据库**：
  - 用于站点、运行记录、站点地图、URL、页面、嵌入向量、内容、审查、发布和指标的 Postgres + pgvector 数据库。
  - Drizzle schema 是新的主 schema 来源；SQLite 仅作为旧 MVP 数据迁移来源保留。
- **MCP 标准输入输出（stdio）工具**：
  - `web_search`：使用配置的提供商进行网页搜索。
  - `ask`：通过本地浏览器会话向配置的模型提问，禁用时回退到搜索。
  - `scrape_url`：获取 URL 并返回可读的页面文本。
- **兼容 OpenAI 的 HTTP API**：
  - `GET /v1/models`
  - `POST /v1/chat/completions`
- 位于 `/` 的管理控制台。
- 位于 `POST /api/scrape` 的管理 HTTP 抓取端点。
- **搜索提供商（Search Providers）**：
  - `scrapling`：默认无需 API Key 的 HTML 搜索路径。
  - `gemini_grounding`：带有 Google Search Grounding 的 Gemini API。
  - `brave`：Brave Search API。
  - `tavily`：Tavily Search API。
- **抓取后端（Scraping Backends）**：
  - `scrapling`：默认的 HTTP 获取器。
  - `scrapling_chromium`：Scrapling 动态 Chromium 获取器。
  - `scrapling_stealthy`：Scrapling 隐秘（stealthy）获取器。
  - `cloakbrowser`：可选的 CloakBrowser 后端。
- **用于 `ask` 的网站对话提供商**：
  - `disabled`：默认值；`ask` 回退到配置的搜索。
  - `deepseek`：通过浏览器向 `https://chat.deepseek.com/` 提问。
  - `chatgpt`：通过浏览器向 `https://chatgpt.com/` 提问。
  - `gemini`：通过浏览器向 `https://gemini.google.com/app` 提问。

## 使用 n8n 的 ContentPilot 工作流

有关使用 n8n 作为工作流编排器、ContentPilot 作为资源获取和工作流控制后端的实际设计，请参阅 [docs/content-factory-n8n.md](docs/content-factory-n8n.md)。

关于本地 n8n 的设置，请参阅 [docs/n8n-local-dev.md](docs/n8n-local-dev.md)。

此 ContentPilot 工作流集成当前包含两个上游 GitHub 项目：

| 上游项目 | 在本项目中的角色 | 安装/部署路径 |
| --- | --- | --- |
| [Zie619/n8n-workflows](https://github.com/Zie619/n8n-workflows) | 用于工作流设计/参考的本地可搜索工作流模板语料库 | 使用 `npm.cmd run n8n:sync-templates` 同步到 `vendor/n8n-workflows` |
| [microsoft/markitdown](https://github.com/microsoft/markitdown) | 将 PDF/DOCX/PPTX/XLSX/HTML/Markdown 源文档转换为 Markdown 研究资产 | Python 可选依赖项 `.[content-factory]` 和 `.[all]` |

初始化 ContentPilot 数据库。默认情况下，这会连接到 `CONTENTPILOT_DATABASE_URL` 指向的 Postgres 数据库，先确保 pgvector extension 存在，再通过 Drizzle 同步 schema：

```bash
python scripts/init_content_factory_db.py
```

在 Windows PowerShell 上：

```powershell
.\scripts\init_content_factory_db.ps1
```

旧的本地 SQLite 数据库不再用于新环境初始化。如需迁移旧数据，请使用 `scripts/migrate_sqlite_to_postgres.py`。

在 n8n 运行后导入本地内容工厂工作流：

```powershell
.\scripts\import_content_factory_workflows.ps1
```

同步并索引公共 n8n 工作流模板语料库：

```powershell
npm.cmd run n8n:sync-templates
```

将同步的 Zie619/n8n-workflows 模板语料库导入 Postgres，以供工作流设计参考：

```powershell
.\.venv-windows-build\Scripts\python.exe scripts\import_n8n_workflow_templates_to_postgres.py
```

模板存储在 `n8n_workflow_templates` 中，包含源路径、分类、节点类型、触发器类型、可搜索文本以及完整的工作流 JSON。

使用 MarkItDown 摄取文档：

```powershell
Copy-Item examples\content-factory\sample-source.md data\inbox\sample-source.md
scripts\run_content_factory_task.cmd seed-topic "document research" --id document-research-demo
scripts\run_content_factory_task.cmd ingest-document --topic-id document-research-demo --file data\inbox\sample-source.md
```

仅使用主域名 URL 运行内容抓取管道。详情请参阅 [docs/content-crawl-workflows.md](docs/content-crawl-workflows.md)：

```powershell
scripts\run_content_factory_task.cmd crawl-run https://example.com
```

抓取管道将网站元数据、站点地图记录、URL 队列条目、原始 HTML、转换后的 Markdown、页面摘要以及摘要向量存储在带有 pgvector 的 Postgres 中。这两个 n8n 工作流是：

```text
Content Crawl - 01 Discover URLs
Content Crawl - 02 Fetch Process Embed
```

验证爬虫发现任务：

```powershell
scripts\run_content_factory_task.cmd crawl-discover https://example.com --limit 20
```

> [!WARNING]
> 仅在您拥有、被授权测试或被允许自动化的网站上使用基于浏览器的抓取。请遵守 robots.txt、网站条款和适用法律。
> 网站对话自动化适用于使用您自己已登录会话的个人研究。本项目不会绕过登录、验证码（CAPTCHA）、付费墙或网站限制。

## 安装

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[all]"
npm install
scrapling install
```

## 运行 Next.js 管理控制台

ContentPilot 管理控制台现在作为一个 Next.js 应用运行，由 Drizzle 和 Postgres/pgvector 提供支持。

```powershell
$env:CONTENTPILOT_DATABASE_URL="postgresql://postgres:Postgres2024%40%23@192.168.0.46:5433/contentpilot"
$env:CONTENTPILOT_API_URL="http://127.0.0.1:8081"
npm.cmd run web:dev
```

打开：

```text
http://127.0.0.1:8080
```

Next.js 控制台占用公共本地端口。它会将兼容的后端 API 路径（如 `/v1/*`、`/api/scrape` 和 `/api/content-factory/*`）代理到 Python API 服务。

Drizzle Schema 和迁移文件位于 `apps/web` 下。pgvector 迁移文件为：

```text
apps/web/drizzle/0000_contentpilot_pgvector.sql
```

生成或推送 Drizzle 迁移：

```powershell
npm.cmd run db:generate
npm.cmd run db:push
```

## 端口策略

默认的本地和 Docker 使用仅暴露一个面向用户的端口：

```text
8080  ContentPilot Next.js 控制台和代理的 API 路径
```

在 Docker Compose 内部，各服务保留其原生端口：

```text
contentpilot:8080  Python FastAPI 搜索/抓取/任务 API
n8n:5678           工作流构建器和调度器
```

对于本地非 Docker 开发，在 `8081` 上运行 Python API，在 `8080` 上运行 Next.js。

如需 CloakBrowser 支持，请根据其自身文档进行安装和配置。该项目通过 `.[cloakbrowser]` 或 `.[all]` 将其作为可选后端保留。

对于无需 CloakBrowser 的轻量级 content-factory Python 安装：

```powershell
pip install -e ".[content-factory]"
npm install
npm.cmd run n8n:sync-templates
```

## 运行 MCP

```bash
contentpilot-mcp
```

Claude/Cursor MCP 配置示例：

```json
{
  "mcpServers": {
    "contentpilot": {
      "command": "contentpilot-mcp",
      "args": [],
      "env": {
        "GEMINI_SEARCH_PROVIDER": "scrapling",
        "GEMINI_SEARCH_SCRAPE_BACKEND": "scrapling"
      }
    }
  }
}
```

## 运行 HTTP API

```bash
contentpilot --host 127.0.0.1 --port 8081
```

使用基于浏览器的抓取后端：

```bash
contentpilot --scrape-backend scrapling_chromium --headless
contentpilot --scrape-backend cloakbrowser --headless
```

为了保持兼容性，旧版命令 `gemini-search` 和 `gemini-search-mcp` 仍会被安装。

## 配置项说明

| 环境变量 | 默认值 | 描述说明 |
| --- | --- | --- |
| `GEMINI_SEARCH_PROVIDER` | `scrapling` | 搜索提供商：可设为 `scrapling`、`gemini_grounding`、`brave` 或 `tavily`。 |
| `GEMINI_SEARCH_SCRAPE_BACKEND` | `scrapling` | 抓取后端：可设为 `scrapling`、`scrapling_chromium`、`scrapling_stealthy` 或 `cloakbrowser`。 |
| `HEADLESS` | MCP/Docker 默认为 `1`，桌面启动器中为 `0` | 基于浏览器的抓取是否开启无头模式。 |
| `GEMINI_SEARCH_PROXY_SERVER` | 为空 | 可选的代理服务器 URL。 |
| `GEMINI_API_KEY` | 为空 | 使用 `gemini_grounding` 时必填。 |
| `GEMINI_MODEL` | `gemini-2.5-flash` | 用于 Grounded 搜索的 Gemini 模型。 |
| `BRAVE_API_KEY` | 为空 | 使用 `brave` 时必填。 |
| `TAVILY_API_KEY` | 为空 | 使用 `tavily` 时必填。 |
| `TAVILY_SEARCH_DEPTH` | `basic` | Tavily 搜索深度，通常为 `basic` 或 `advanced`。 |
| `WEB_CHAT_PROVIDER` | `disabled` | 可设为 `disabled`、`deepseek`、`chatgpt` 或 `gemini`。控制 MCP 的 `ask` 路径。 |
| `WEB_CHAT_BACKEND` | `playwright` | 网页对话自动化的后端，可设为 `playwright` 或 `cloakbrowser`。 |
| `WEB_CHAT_HEADLESS` | 本地默认为 `0` | 首次登录使用 `0`（有头），在会话建立后才能使用 `1`（无头）。 |
| `WEB_CHAT_PROFILE_DIR` | `profiles/web-chat/<provider>` | 用于持久化保存网站登录会话的浏览器用户配置文件目录。 |

## 网页对话研究模式（Website Chat Research Mode）

首先在有头（Headed）模式下运行，以便您可以手动登录：

```powershell
$env:WEB_CHAT_PROVIDER="deepseek"
$env:WEB_CHAT_BACKEND="playwright"
$env:WEB_CHAT_HEADLESS="0"
$env:WEB_CHAT_PROFILE_DIR="$PWD\profiles\web-chat\deepseek"
.\.venv-windows-build\Scripts\contentpilot.exe --host 127.0.0.1 --port 8081
```

在浏览器中打开 Next.js 控制台 `http://127.0.0.1:8080/`，通过代理的 API 路径发送一条测试提示词，如果网站要求登录，请在弹出的浏览器窗口中完成登录。在配置文件成功登录后，MCP `ask` 工具将会直接复用该网站会话。MCP `web_search` 仍是通用的搜索工具，不会使用该模型网站。

等效的 MCP 环境配置：

```json
{
  "WEB_CHAT_PROVIDER": "deepseek",
  "WEB_CHAT_BACKEND": "playwright",
  "WEB_CHAT_HEADLESS": "0",
  "WEB_CHAT_PROFILE_DIR": "profiles/web-chat/deepseek",
  "GEMINI_SEARCH_PROVIDER": "scrapling"
}
```

## Docker 部署

```bash
docker compose up -d --build
```

Docker 镜像会安装 `.[all]` 并运行 `scrapling install`，以便可以使用 Scrapling 浏览器辅助获取器。默认运行模式是较轻量的 `scrapling` 后端。

生产部署使用独立的 Next.js Web 镜像，避免容器启动时重新安装依赖和构建：

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

生产 compose 会构建 `contentpilot` Python API/任务执行层、`contentpilot-web` Next.js 后台、`n8n` 工作流服务和 `caddy` 公网入口。

## API 调用示例

调用对话接口：

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"contentpilot\",\"messages\":[{\"role\":\"user\",\"content\":\"latest AI news today\"}]}"
```

抓取网页：

```bash
curl http://localhost:8080/api/scrape \
  -H "Content-Type: application/json" \
  -d "{\"url\":\"https://example.com\",\"selector\":\"body\"}"
```
