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
- 支持连接同一运行环境内的本地 Chrome CDP 实例，也支持自动拉起浏览器。
- 支持持久化浏览器用户目录，复用 Cookie，降低 CAPTCHA 干扰。
- 默认使用 Playwright 管理 Chromium，也支持可选 CloakBrowser 后端和代理配置。
- 支持 Docker Compose 部署。

## 技术栈

| 类型 | 技术 |
| --- | --- |
| 语言 | Python 3.10+ |
| MCP 服务 | `mcp[cli]`、`FastMCP`、stdio transport |
| HTTP API | FastAPI、Uvicorn |
| 浏览器控制 | Chrome DevTools Protocol、WebSocket |
| 可选自动化架构 | Playwright、CloakBrowser |
| 浏览器 | Playwright Chromium、Chrome、Microsoft Edge 或自定义 Chromium-compatible 浏览器 |
| 可选浏览器后端 | request、Playwright、CloakBrowser |
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
- 如果使用 CloakBrowser 后端，需要额外安装可选依赖并按其官方文档准备运行环境。

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

安装后默认包含 Playwright 后端。如需预下载 Playwright Chromium：

```bash
playwright install chromium
```

如需使用 CloakBrowser 后端：

```bash
pip install -e ".[cloakbrowser]"
python -m cloakbrowser install
```

也可以安装所有可选后端：

```bash
pip install -e ".[all]"
playwright install chromium
```

注意：CloakBrowser 的授权、二进制下载、平台支持和使用边界以其官方文档为准。请仅用于你有权限的网站、内部系统或授权测试。

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

如果要连接同一运行环境内已经打开并开启 CDP 的 Chrome：

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
| `--cdp-url` | 无 | 连接本机 / 容器内 Chrome CDP，仅允许 `localhost`、`127.0.0.1` 或 `::1`。 |
| `--channel` | `chrome` | 浏览器类型，可选 `chrome`、`msedge`、`chromium`。 |
| `--no-headless` | 关闭 | 显示浏览器窗口，便于手动处理 CAPTCHA。 |
| `--user-data-dir` | 无 | 指定持久化 Chrome 用户目录。 |
| `--browser-backend` | `playwright` | 后端，可选 `request`、`playwright`、`cloakbrowser`。 |
| `--proxy-server` | 无 | Chrome 代理，例如 `socks5://127.0.0.1:7897`。 |

### 后端选择

| 后端 | 说明 | 适合场景 |
| --- | --- | --- |
| `request` | 直接用 HTTP 请求访问 Google AI Mode，不启动浏览器。 | 资源最省，但最不稳定，容易受页面结构和服务端策略影响。 |
| `playwright` | 使用 Playwright 启动和控制 Chromium 页面。 | 默认推荐，适合 Docker、VPS 和长期维护。 |
| `cloakbrowser` | 使用 CloakBrowser 的 Playwright-like API。 | 仅适合授权测试、自有系统或明确允许的自动化场景。 |

示例：

```bash
gemini-search --browser-backend request --port 8080
gemini-search --browser-backend playwright --channel chromium --port 8080
gemini-search --browser-backend cloakbrowser --port 8080
gemini-search --browser-backend playwright --no-headless --user-data-dir ./profile
```

## Web 测试控制台

HTTP 服务内置一个轻量测试控制台：

```text
http://localhost:8080/
```

部署到 VPS 后：

```text
https://你的域名/
```

控制台能力：

- 查看当前后端和健康状态。
- 切换 `request`、`playwright`、`cloakbrowser` 后端。
- 切换有头 / 无头模式。
- 配置浏览器通道、Profile 目录、代理、本地 CDP URL。
- 应用配置并重启后端。
- 发送测试 Prompt 并展示响应、耗时和错误信息。
- 检查 `/v1/models`。

管理 API：

| 接口 | 说明 |
| --- | --- |
| `GET /api/health` | 查看运行状态。 |
| `GET /api/runtime` | 查看当前运行时配置。 |
| `PUT /api/runtime` | 更新配置并重启浏览器后端。 |
| `POST /api/runtime/restart` | 使用当前配置重启浏览器后端。 |
| `POST /api/test` | 发送测试问题。 |

生产环境建议设置 `ADMIN_TOKEN`：

```env
ADMIN_TOKEN=替换成随机长字符串
```

设置后，测试控制台会在首次请求管理 API 时要求输入 token，并通过 `Authorization: Bearer <token>` 调用接口。不要在公网部署时留空 `ADMIN_TOKEN`。

如果浏览器或外部网络初始化失败，HTTP 服务仍会启动，测试控制台仍可访问。页面会显示后端未就绪和最近错误，方便修改代理、后端或 Profile 后重启验证。

## 环境变量

MCP 服务主要通过环境变量配置，HTTP 服务也会读取其中一部分变量：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CDP_URL` | 无 | 本机 / 容器内 Chrome DevTools 地址。设置后不会自动启动新浏览器，仅允许 `localhost`、`127.0.0.1` 或 `::1`。 |
| `ADMIN_TOKEN` | 无 | Web 测试控制台和管理 API 的访问 token。生产环境建议必填。 |
| `BROWSER_CHANNEL` | `chrome` | 浏览器类型：`chrome`、`msedge`、`chromium`。 |
| `HEADLESS` | `1` | 是否无头运行。设为 `0` 时显示浏览器窗口。 |
| `GEMINI_SEARCH_USER_DATA_DIR` | 无 | 持久化 Chrome 用户目录。 |
| `GEMINI_SEARCH_CDP_PORT` | `19250` | 自动启动浏览器时使用的 CDP 端口。 |
| `GEMINI_SEARCH_PROFILE_ROTATION_SECONDS` | `0` | Docker 部署时的 Profile 轮换周期，单位秒；`0` 表示不轮换。 |
| `GEMINI_SEARCH_BROWSER_BACKEND` | `playwright` | 后端：`request`、`playwright` 或 `cloakbrowser`。 |
| `GEMINI_SEARCH_PROXY_SERVER` | 无 | Chrome 代理地址。 |
| `GEMINI_SEARCH_CHROME_EXTRA_ARGS` | 无 | 追加 Chrome 启动参数，Docker 中常用 `--no-sandbox --disable-dev-shm-usage --disable-gpu`。 |
| `CHROME_PATH` | 无 | 自定义 Chromium-compatible 浏览器可执行文件路径，主要供 Playwright 后端使用。 |

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

如果普通无头运行持续遇到 CAPTCHA，可以尝试使用可见模式初始化持久化 Profile，或配置代理后重启服务。

## Docker 部署

### 本地 Docker 启动

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

### VPS HTTPS 部署

生产部署推荐使用 `docker-compose.prod.yml`。该配置包含两个服务：

| 服务 | 说明 |
| --- | --- |
| `gemini-search` | Python HTTP API 服务，运行在 Docker 内网的 `8080` 端口。 |
| `caddy` | HTTPS 反向代理，自动申请和续期 Let's Encrypt 证书。 |

容器数量建议：

| 方案 | 容器数 | 说明 |
| --- | --- | --- |
| 最小 HTTP 服务 | 1 个 | 只运行 `gemini-search`，对外暴露 `8080`，由你已有的 Nginx、宝塔、1Panel、Traefik 或 Cloudflare Tunnel 负责 HTTPS。 |
| 推荐 HTTPS 部署 | 2 个 | `gemini-search` + `caddy`。Caddy 负责公网 `80/443` 和 HTTPS 证书。 |
| 独立浏览器服务 | 3 个或更多 | 仅当你要把浏览器、代理池、Profile 管理拆成独立服务时考虑。当前项目不需要这样做。 |

默认 Docker 镜像中，Python 服务、Playwright 控制库、CloakBrowser Python 包和 Playwright Chromium 都在 `gemini-search` 同一个容器内。Chromium 不是单独容器。

生产默认参数：

| 项目 | 默认值 |
| --- | --- |
| 外部 HTTP 端口 | `80`，由 Caddy 监听 |
| 外部 HTTPS 端口 | `443`，由 Caddy 监听 |
| 内部 API 端口 | `8080`，仅 Docker 内网访问 |
| 测试控制台 | `https://你的域名/` |
| OpenAI Base URL | `https://你的域名/v1` |
| 浏览器后端 | `playwright` |
| 浏览器模式 | headless |
| Profile 目录 | `/data/chrome-profile`，挂载到 Docker volume |
| Profile 轮换 | 默认关闭，`GEMINI_SEARCH_PROFILE_ROTATION_SECONDS=0` |
| 容器外部访问 | 默认 Docker bridge 出站网络，可访问外部 Google/Gemini 服务 |

部署前准备：

- 一台 Linux VPS。
- 已安装 Docker 和 Docker Compose 插件。
- 一个域名，例如 `search.example.com`。
- 将域名 A 记录解析到 VPS 公网 IP。
- VPS 防火墙和云厂商安全组放行 `80`、`443` 端口。

#### Ubuntu 一键脚本部署

项目提供了 Ubuntu VPS 部署脚本：

```bash
scripts/deploy_ubuntu_docker.sh
```

运行脚本前，必须先修改脚本顶部变量：

```bash
DOMAIN="search.example.com"
ACME_EMAIL="admin@example.com"
```

按你的实际环境改成：

```bash
DOMAIN="你的域名"
ACME_EMAIL="你的邮箱"
```

可选变量：

```bash
REPO_URL="https://github.com/rainco2008/ai-arena-mcp.git"
APP_DIR="/opt/ai-arena-mcp"
ADMIN_TOKEN=""
GEMINI_SEARCH_BROWSER_BACKEND="playwright"
GEMINI_SEARCH_PROXY_SERVER=""
GEMINI_SEARCH_PROFILE_ROTATION_SECONDS="0"
```

变量说明：

| 变量 | 是否必填 | 说明 |
| --- | --- | --- |
| `DOMAIN` | 是 | 对外访问域名，必须已经解析到 VPS 公网 IP。 |
| `ACME_EMAIL` | 是 | Caddy / Let's Encrypt 申请 HTTPS 证书使用的邮箱。 |
| `REPO_URL` | 否 | GitHub 仓库地址，默认使用当前项目仓库。 |
| `APP_DIR` | 否 | 项目部署目录，默认 `/opt/ai-arena-mcp`。 |
| `ADMIN_TOKEN` | 否 | Web 测试控制台和管理 API 的 token。生产环境建议设置随机长字符串。 |
| `GEMINI_SEARCH_BROWSER_BACKEND` | 否 | 后端，默认 `playwright`。可选 `request`、`playwright`、`cloakbrowser`。 |
| `GEMINI_SEARCH_PROXY_SERVER` | 否 | Chrome 代理地址，例如 `socks5://127.0.0.1:7897`。 |
| `GEMINI_SEARCH_PROFILE_ROTATION_SECONDS` | 否 | Profile 轮换周期，单位秒；默认 `0` 不轮换，例如 `86400` 表示每天轮换一次。 |

上传或拉取项目后，在项目目录运行：

```bash
sudo bash scripts/deploy_ubuntu_docker.sh
```

脚本会自动执行：

- 检查 Docker 是否已安装。
- 检查 Docker Compose 插件是否可用。
- 检查 `git` 是否已安装。
- 如果 Docker 服务未运行，则尝试启动 Docker 服务。
- 如果系统安装了 UFW，则放行 `80/tcp` 和 `443/tcp`。
- 克隆或更新项目到 `APP_DIR`。
- 生成 `.env.production`。
- 如果 `ADMIN_TOKEN` 为空，自动生成随机 token。
- 使用 `docker-compose.prod.yml` 构建并启动服务。
- 输出测试控制台地址、API 地址和 `ADMIN_TOKEN`。

如果脚本提示 Docker 或 Docker Compose 插件未安装，请先手工安装。

Ubuntu 手工安装 Docker 示例：

```bash
# 1. 更新 apt 索引并安装基础依赖
sudo apt-get update
sudo apt-get install -y ca-certificates curl

# 2. 添加 Docker 官方 GPG key
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# 3. 添加 Docker 官方 apt 源
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 4. 安装 Docker Engine 和 Compose 插件
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 5. 启动 Docker 并设置开机自启
sudo systemctl enable --now docker

# 6. 验证 Docker 和 Compose 插件
docker --version
docker compose version
```

Docker 官方文档：

- Docker Engine for Ubuntu: `https://docs.docker.com/engine/install/ubuntu/`
- Docker Compose plugin: `https://docs.docker.com/compose/install/linux/`

脚本完成后验证：

```bash
curl https://你的域名/v1/models
```

浏览器访问测试控制台：

```text
https://你的域名/
```

如果脚本自动生成了 `ADMIN_TOKEN`，页面首次调用管理 API 时会弹窗要求输入该 token。

#### 手动部署

复制环境变量模板：

```bash
cp .env.production.example .env.production
```

编辑 `.env.production`：

```env
DOMAIN=search.example.com
ACME_EMAIL=admin@example.com
ADMIN_TOKEN=
GEMINI_SEARCH_BROWSER_BACKEND=playwright
GEMINI_SEARCH_PROXY_SERVER=
GEMINI_SEARCH_PROFILE_ROTATION_SECONDS=0
```

启动服务：

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
```

查看日志：

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml logs -f
```

验证 HTTPS 访问：

```bash
curl https://search.example.com/v1/models
```

验证聊天接口：

```bash
curl https://search.example.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"gemini-search\",\"messages\":[{\"role\":\"user\",\"content\":\"今天有哪些重要科技新闻？\"}]}"
```

更新部署：

```bash
git pull
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
```

停止服务：

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml down
```

生产部署说明：

- Caddy 会自动申请 HTTPS 证书，首次启动时域名必须已经解析到 VPS。
- `gemini-search` 不直接暴露公网端口，只由 Caddy 反向代理访问。
- `gemini-search` 容器使用 Docker 默认出站网络，并配置 `1.1.1.1`、`8.8.8.8` 作为 DNS 兜底，用于访问外部 Google/Gemini 服务。
- Chrome profile 持久化在 Docker volume `chrome-profile` 中，用于复用 Cookie。
- 如果设置了 `GEMINI_SEARCH_PROFILE_ROTATION_SECONDS`，容器会按周期使用新的 Profile 目录重启 `gemini-search` 服务。轮换期间会有短暂不可用。
- 如果遇到 Google CAPTCHA，可以临时改成非 headless 模式在有图形环境的机器上初始化 profile，或配置代理后重启服务。
- 如果 VPS 内存较小，Chromium 可能不稳定，建议至少 2 GB 内存，并保留 `shm_size: "2gb"`。

#### CloakBrowser / 自定义浏览器说明

当前 Docker 镜像会安装 `cloakbrowser` Python 包，但默认仍运行 Playwright Chromium 后端。CloakBrowser 的二进制下载、授权方式、平台支持和启动参数需要以官方文档为准，因此生产环境不默认自动启用。

启用 CloakBrowser 后端：

```env
GEMINI_SEARCH_BROWSER_BACKEND=cloakbrowser
HEADLESS=1
```

如果需要在构建或启动前预下载 CloakBrowser 二进制，可以在容器内执行：

```bash
python -m cloakbrowser install
python -m cloakbrowser info
```

如果你有明确的 CloakBrowser Linux 可执行文件，并且它兼容 Chromium 启动参数，可以改用自定义浏览器路径：

```env
CHROME_PATH=/path/to/cloakbrowser
BROWSER_CHANNEL=chromium
GEMINI_SEARCH_CDP_PORT=19250
GEMINI_SEARCH_CHROME_EXTRA_ARGS="--remote-debugging-address=127.0.0.1 --no-sandbox --disable-dev-shm-usage"
```

如果 CloakBrowser 在同一个容器或同一台运行环境内由本地进程启动，并且已经开放本地 CDP 地址，可以让本项目直接连接：

```env
CDP_URL=http://127.0.0.1:9222
```

注意事项：

- 不要把 CDP 端口直接暴露到公网；CDP 几乎等同于浏览器远程控制权限。
- 当前代码会拒绝非本机地址的 `CDP_URL`；Docker 部署中 CDP 只能连接容器内浏览器，不连接宿主机或公网浏览器。
- Profile 轮换可以通过 `GEMINI_SEARCH_PROFILE_ROTATION_SECONDS` 实现；例如 `86400` 表示每天重启服务并使用新的 Profile。
- 如果要把 CloakBrowser 自动安装进镜像，建议先确认官方 Linux 下载 URL、校验方式、授权方式和无头/远程调试启动参数，再扩展 Dockerfile。

## 开发与调试

直接运行 HTTP 服务模块：

```bash
python -m gemini_search --port 8080
```

直接运行 MCP 模块：

```bash
python -m gemini_search_mcp
```

使用同一运行环境内的本地 Chrome 调试端口：

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
- 如果 Google 触发 CAPTCHA，需要手动验证、复用持久化 Profile，或按授权场景评估自定义浏览器后端。
- Docker 环境中的浏览器依赖和沙箱配置可能需要按部署平台调整。

## 许可证

MIT
