# gemini-search-mcp

<p align="center">
  <img src="banner.png" width="700" alt="gemini-search-mcp">
</p>

<p align="center">
  <img src="logo.png" width="120" alt="logo">
</p>

`gemini-search-mcp` 是一个基于 Google AI Mode / Gemini 搜索能力的 MCP 服务，同时提供 OpenAI 兼容的 HTTP API。它可以让 Claude Desktop、Claude Code、Cursor、Windsurf、Cline 等 MCP 客户端获得实时联网搜索能力，也可以作为普通 HTTP 服务被 OpenAI SDK 兼容客户端调用。

## 项目功能

- 提供 MCP stdio 服务，暴露 `web_search` 和 `ask` 两个工具。
- 提供 OpenAI 兼容接口：`/v1/models`、`/v1/chat/completions`。
- 通过真实 Chrome / Edge / Chromium 浏览器和 Chrome DevTools Protocol 发起查询。
- 支持连接已有 Chrome CDP 实例，也支持自动拉起浏览器。
- 支持持久化浏览器用户目录，复用 Cookie，降低 CAPTCHA 干扰。
- 支持可选的 `undetected-chromedriver` 后端和代理配置。
- 支持 Docker Compose 部署。

## 技术栈

| 类型 | 技术 |
| --- | --- |
| 语言 | Python 3.10+ |
| MCP 服务 | `mcp[cli]`、`FastMCP`、stdio transport |
| HTTP API | FastAPI、Uvicorn |
| 浏览器控制 | Chrome DevTools Protocol、WebSocket |
| 浏览器 | Chrome、Microsoft Edge 或 Chromium |
| 可选浏览器后端 | undetected-chromedriver、Selenium |
| 部署 | Docker、Docker Compose |
| 包管理 / 构建 | setuptools、`pyproject.toml` |

## 目录结构

```text
.
├── gemini_search/           # OpenAI 兼容 HTTP API 和搜索引擎实现
│   ├── engine.py            # 浏览器启动、CDP 连接、AI Mode 查询与解析
│   ├── server.py            # FastAPI 服务入口
│   └── __main__.py
├── gemini_search_mcp/       # MCP stdio 服务入口
│   ├── __init__.py
│   └── __main__.py
├── scripts/                 # CAPTCHA / Chrome 配置探测脚本
├── mcp_server.py            # MCP 服务兼容入口
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## 环境要求

- Python 3.10 或更高版本。
- 已安装 Chrome、Microsoft Edge 或 Chromium。
- 如果使用 Docker 部署，需要安装 Docker 和 Docker Compose。
- 如果使用 `undetected` 后端，需要额外安装可选依赖。

## 本地安装

进入项目目录：

```bash
cd ai-arena-mcp
```

建议创建虚拟环境：

```bash
python -m venv .venv
```

Windows PowerShell 激活：

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS / Linux 激活：

```bash
source .venv/bin/activate
```

安装项目：

```bash
pip install -e .
```

如需使用 `undetected-chromedriver` 后端：

```bash
pip install -e ".[undetected]"
```

## 启动 MCP 服务

MCP 服务使用 stdio transport，适合由 Claude Desktop、Claude Code、Cursor 等客户端拉起：

```bash
gemini-search-mcp
```

也可以使用兼容入口：

```bash
python mcp_server.py
```

### MCP 工具

| 工具 | 参数 | 说明 |
| --- | --- | --- |
| `web_search` | `query: str` | 使用 Google AI Mode 进行实时网页搜索，并返回综合回答。 |
| `ask` | `prompt: str` | 向 Google AI Mode 提问，由 AI Mode 自动判断是否需要联网搜索。 |

### Claude Code 配置示例

```bash
claude mcp add gemini-search -- gemini-search-mcp
```

### Claude Desktop 配置示例

在 `claude_desktop_config.json` 中加入：

```json
{
  "mcpServers": {
    "gemini-search": {
      "command": "gemini-search-mcp",
      "args": [],
      "env": {
        "BROWSER_CHANNEL": "chrome",
        "HEADLESS": "1"
      }
    }
  }
}
```

如果要连接已经打开并开启 CDP 的 Chrome：

```json
{
  "mcpServers": {
    "gemini-search": {
      "command": "gemini-search-mcp",
      "args": [],
      "env": {
        "CDP_URL": "http://127.0.0.1:9222"
      }
    }
  }
}
```

## 启动 OpenAI 兼容 HTTP API

默认监听 `0.0.0.0:8080`：

```bash
gemini-search --port 8080
```

指定主机和端口：

```bash
gemini-search --host 127.0.0.1 --port 8080
```

接口信息：

| 项目 | 值 |
| --- | --- |
| Base URL | `http://localhost:8080/v1` |
| 模型名 | `gemini-search` |
| API Key | 任意字符串，当前服务不校验 |

请求示例：

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"gemini-search\",\"messages\":[{\"role\":\"user\",\"content\":\"今天有哪些重要 AI 新闻？\"}]}"
```

流式请求示例：

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"gemini-search\",\"stream\":true,\"messages\":[{\"role\":\"user\",\"content\":\"总结最近的半导体行业新闻\"}]}"
```

## 常用启动参数

`gemini-search` HTTP 服务支持以下参数：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--host` | `0.0.0.0` | HTTP 服务监听地址。 |
| `--port` | `8080` | HTTP 服务监听端口。 |
| `--cdp-url` | 无 | 连接已有 Chrome CDP，例如 `http://127.0.0.1:9222`。 |
| `--channel` | `chrome` | 浏览器类型，可选 `chrome`、`msedge`、`chromium`。 |
| `--no-headless` | 关闭 | 显示浏览器窗口，便于手动处理 CAPTCHA。 |
| `--user-data-dir` | 无 | 指定持久化 Chrome 用户目录。 |
| `--browser-backend` | `subprocess` | 浏览器启动后端，可选 `subprocess`、`undetected`。 |
| `--proxy-server` | 无 | Chrome 代理，例如 `socks5://127.0.0.1:7897`。 |
| `--chromedriver-path` | 无 | `undetected` 后端使用的 chromedriver 路径。 |

## 环境变量

MCP 服务主要通过环境变量配置，HTTP 服务也会读取其中一部分变量：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CDP_URL` | 无 | 已有 Chrome DevTools 地址。设置后不会自动启动新浏览器。 |
| `BROWSER_CHANNEL` | `chrome` | 浏览器类型：`chrome`、`msedge`、`chromium`。 |
| `HEADLESS` | `1` | 是否无头运行。设为 `0` 时显示浏览器窗口。 |
| `GEMINI_SEARCH_USER_DATA_DIR` | 无 | 持久化 Chrome 用户目录。 |
| `GEMINI_SEARCH_CDP_PORT` | `19250` | 自动启动浏览器时使用的 CDP 端口。 |
| `GEMINI_SEARCH_BROWSER_BACKEND` | `subprocess` | 浏览器后端：`subprocess` 或 `undetected`。 |
| `GEMINI_SEARCH_PROXY_SERVER` | 无 | Chrome 代理地址。 |
| `GEMINI_SEARCH_CHROMEDRIVER` | 无 | chromedriver 可执行文件路径。 |
| `UC_CHROMEDRIVER` | 无 | `undetected-chromedriver` 的 chromedriver 路径别名。 |
| `UC_CHROME_BINARY` | 无 | `undetected` 后端使用的 Chrome 可执行文件路径。 |
| `CHROME_PATH` | 无 | Chrome 可执行文件路径。 |

## 持久化 Chrome Profile 与 CAPTCHA 处理

首次运行时，如果 Google 要求 CAPTCHA，建议使用可见浏览器窗口并指定持久化用户目录，手动完成验证后再复用该目录：

```bash
gemini-search --no-headless --user-data-dir "$HOME/.local/share/gemini-search-mcp/chrome-profile"
```

之后可以无头复用：

```bash
GEMINI_SEARCH_USER_DATA_DIR="$HOME/.local/share/gemini-search-mcp/chrome-profile" gemini-search
```

Windows PowerShell 示例：

```powershell
$env:GEMINI_SEARCH_USER_DATA_DIR="$env:USERPROFILE\.gemini-search-mcp\chrome-profile"
gemini-search --no-headless
```

如果普通 Chrome 后端持续遇到 CAPTCHA，可以尝试安装可选依赖并使用 `undetected` 后端：

```bash
pip install -e ".[undetected]"
gemini-search --browser-backend undetected --no-headless
```

## Docker 部署

构建并后台启动：

```bash
docker compose up -d --build
```

查看日志：

```bash
docker compose logs -f
```

停止服务：

```bash
docker compose down
```

Docker Compose 默认将容器内 `8080` 端口映射到本机 `8080`：

```text
http://localhost:8080/v1
```

注意：当前 `Dockerfile` 会执行 `playwright install chromium --with-deps`，但项目运行时主要通过本项目代码启动 Chrome / Chromium 并使用 CDP。若在精简容器中运行异常，需要检查 Chromium 可执行文件路径、依赖库和沙箱权限。

## 开发与调试

直接运行 HTTP 服务模块：

```bash
python -m gemini_search --port 8080
```

直接运行 MCP 模块：

```bash
python -m gemini_search_mcp
```

使用已有 Chrome 调试端口：

```bash
chrome --remote-debugging-port=9222 --user-data-dir=/tmp/gemini-search-debug
```

然后启动服务：

```bash
CDP_URL=http://127.0.0.1:9222 gemini-search --port 8080
```

## 工作原理

项目启动后会创建或连接一个真实浏览器实例，通过 CDP 在浏览器上下文中执行请求。核心流程如下：

```text
MCP / HTTP 客户端发起问题
  -> AIModeEngine 启动或连接 Chrome
  -> 通过 CDP 在真实浏览器环境中访问 Google AI Mode
  -> 提取和解析返回内容
  -> 将综合回答返回给 MCP 工具或 HTTP API 调用方
```

这种方式依赖真实浏览器环境，能够复用浏览器 Cookie、TLS/HTTP 指纹和代理配置，但也意味着项目对浏览器版本、Google 页面结构和 CAPTCHA 状态较敏感。

## 已知限制

- 必须安装可用的 Chrome、Edge 或 Chromium。
- Google 页面结构变化可能导致解析逻辑失效。
- 无内置多轮会话记忆，每次请求主要按单次问题处理。
- 流式响应是分块输出，不保证等同于模型原生 token 流。
- 如果 Google 触发 CAPTCHA，需要手动验证、复用持久化 Profile，或尝试 `undetected` 后端。
- Docker 环境中的浏览器依赖和沙箱配置可能需要按部署平台调整。

## 许可证

MIT
