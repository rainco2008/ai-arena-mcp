"""Lightweight engine for Google AI Mode."""
from __future__ import annotations

import asyncio
import json
import os
import random
import shlex
import shutil
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlparse

try:
    import websockets
except ImportError:  # pragma: no cover - surfaced at runtime by _connect_cdp
    websockets = None


_ASK_JS = """
(async (q) => {
    try {
        const pageUrl = %SEARCH_URL% + '?q=' + encodeURIComponent(q) + '&hl=en-GB&gl=GB&udm=50&aep=1&ntc=1';
        const r1 = await fetch(pageUrl, {credentials:'include'});
        if (!r1.ok) return {error:'fetch_status_' + r1.status, htmlLen:0};
        const html = await r1.text();
        const m = (p) => { const x = html.match(p); return x ? x[1] : ''; };
        const srtst = m(/data-srtst="([^"]+)"/);
        if (!srtst) return {error:'no_token', htmlLen:html.length, preview:html.substring(0,200)};
        const xsrf = m(/data-xsrf-folwr-token="([^"]+)"/);
        const garc = m(/data-garc="([^"]+)"/);
        const lro = m(/data-lro-token="([^"]+)"/);
        const mlros = m(/data-lro-signature="([^"]+)"/);
        const ei = m(/data-ei="([^"]+)"/);
        const stkp = m(/data-stkp="([^"]+)"/);
        const ved = m(/aria-current="page"[^>]*data-ved="([^"]+)"/);
        const sca = m(/sca_esv=([a-f0-9]+)/);
        const p = new URLSearchParams({srtst,garc,mlro:lro,mlros,ei,q,yv:'3',vet:'1'+ved+'..i',ved,aep:'1',gl:'GB',hl:'en-GB',sca_esv:sca,udm:'50',stkp,cs:'0',async:'_fmt:adl,_xsrf:'+xsrf});
        const r2 = await fetch(%ASYNC_URL% + '?' + p.toString(), {credentials:'include'});
        if (!r2.ok) return {error:'folwr_status_' + r2.status};
        const fh = await r2.text();
        const div = document.createElement('div');
        div.innerHTML = fh;
        // Remove non-content elements
        div.querySelectorAll('script,style,button,noscript,[aria-hidden="true"],span[style*="display:none"],.LGKDTe,.SGF5Lb').forEach(x => x.remove());
        // Collect text from ALL answer blocks: pTRUV first (short answers), then n6owBd (paragraphs)
        let parts = [];
        div.querySelectorAll('.pTRUV').forEach(el => {
            const t = el.textContent.trim();
            if (t && t.length > 1) parts.push(t);
        });
        div.querySelectorAll('.n6owBd').forEach(el => {
            const t = el.textContent.trim();
            if (t && t.length > 10) parts.push(t);
        });
        // Fallback: all dir=ltr blocks minus citation containers
        if (!parts.length) {
            div.querySelectorAll('.mZJni,.XEqVsf,.ub891').forEach(x => x.remove());
            div.querySelectorAll('[dir="ltr"]').forEach(el => {
                const t = el.textContent.trim();
                if (t.length > 30) parts.push(t);
            });
        }
        let text = parts.join('\\n\\n');
        // Clean trailing UI noise
        const noise = ['Copy','Share','Good response','Bad response','About this result','Show all','AI responses may include mistakes','Tell me which'];
        for (const n of noise) { while (text.endsWith(n)) text = text.slice(0, -n.length).trim(); }
        return {ok:true, answer:text, folwrLen:fh.length};
    } catch(e) {
        return {error:'js_exception', message:e.message};
    }
})(%QUERY%)
"""

_STEALTH_INIT_JS = """
(() => {
    const defineGetter = (target, prop, getter) => {
        try {
            Object.defineProperty(target, prop, {
                get: getter,
                configurable: true,
            });
        } catch (_) {}
    };

    defineGetter(Navigator.prototype, 'webdriver', () => undefined);
    defineGetter(Navigator.prototype, 'languages', () => ['en-GB', 'en']);
    defineGetter(Navigator.prototype, 'platform', () => 'Win32');
    defineGetter(Navigator.prototype, 'hardwareConcurrency', () => 8);
    defineGetter(Navigator.prototype, 'deviceMemory', () => 8);
    defineGetter(Navigator.prototype, 'maxTouchPoints', () => 0);

    const pluginData = [
        {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format'},
        {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: ''},
        {name: 'Native Client', filename: 'internal-nacl-plugin', description: ''},
    ];
    const plugins = pluginData.map((plugin) => ({
        ...plugin,
        length: 1,
        0: {type: 'application/pdf', suffixes: 'pdf', description: plugin.description},
    }));
    Object.defineProperties(plugins, {
        length: {value: pluginData.length},
        item: {value: (index) => plugins[index] || null},
        namedItem: {value: (name) => plugins.find((plugin) => plugin.name === name) || null},
        refresh: {value: () => undefined},
    });
    defineGetter(Navigator.prototype, 'plugins', () => plugins);
    defineGetter(Navigator.prototype, 'mimeTypes', () => ({
        length: 1,
        0: {type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format'},
        item(index) { return this[index] || null; },
        namedItem(name) { return name === 'application/pdf' ? this[0] : null; },
    }));

    window.chrome = window.chrome || {};
    window.chrome.runtime = window.chrome.runtime || {};
    window.chrome.app = window.chrome.app || {};

    const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
    if (originalQuery) {
        window.navigator.permissions.query = (parameters) => (
            parameters && parameters.name === 'notifications'
                ? Promise.resolve({state: Notification.permission})
                : originalQuery.call(window.navigator.permissions, parameters)
        );
    }

    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) return 'Google Inc. (Intel)';
        if (parameter === 37446) return 'ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)';
        return getParameter.call(this, parameter);
    };
})();
"""



def _env_or_value(value: Optional[str], *env_names: str) -> Optional[str]:
    """Return an explicit value, or the first non-empty environment value."""
    if value:
        return value
    for name in env_names:
        candidate = os.environ.get(name)
        if candidate:
            return candidate
    return None


async def _maybe_await(value):
    if hasattr(value, "__await__"):
        return await value
    return value


def _normalize_browser_backend(backend: Optional[str]) -> str:
    value = (backend or "playwright").strip().lower()
    aliases = {
        "playwright": "playwright",
        "pw": "playwright",
        "cloak": "cloakbrowser",
        "cloakbrowser": "cloakbrowser",
    }
    if value not in aliases:
        raise ValueError(
            "browser_backend must be one of: playwright, cloakbrowser"
        )
    return aliases[value]


def _google_base_url() -> str:
    value = os.environ.get("GEMINI_SEARCH_GOOGLE_BASE_URL", "https://www.google.co.uk")
    value = value.rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("GEMINI_SEARCH_GOOGLE_BASE_URL must be an HTTP URL")
    return value


def _warmup_query() -> str:
    configured = os.environ.get("GEMINI_SEARCH_WARMUP_QUERY")
    if configured:
        return random.choice([item.strip() for item in configured.split("|") if item.strip()])
    return random.choice(
        [
            "latest UK technology news and weather in London this week",
            "train travel updates from London to Manchester today",
            "best independent coffee shops near central London",
            "UK science and innovation news this week",
            "weekend events in London and South East England",
            "current transport and weather updates for Greater London",
            "recent renewable energy news in the United Kingdom",
            "what is happening in UK tech startups this week",
        ]
    )


def _default_user_data_dir() -> str:
    return str((Path.cwd() / "profiles" / "default").resolve())


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _browser_context_options() -> dict:
    width = _env_int("GEMINI_SEARCH_VIEWPORT_WIDTH", 1365)
    height = _env_int("GEMINI_SEARCH_VIEWPORT_HEIGHT", 768)
    screen_width = _env_int("GEMINI_SEARCH_SCREEN_WIDTH", 1920)
    screen_height = _env_int("GEMINI_SEARCH_SCREEN_HEIGHT", 1080)
    return {
        "viewport": {"width": width, "height": height},
        "screen": {"width": screen_width, "height": screen_height},
        "device_scale_factor": _env_float("GEMINI_SEARCH_DEVICE_SCALE_FACTOR", 1.0),
        "is_mobile": False,
        "has_touch": False,
        "locale": os.environ.get("GEMINI_SEARCH_LOCALE", "en-GB"),
        "timezone_id": os.environ.get("GEMINI_SEARCH_TIMEZONE_ID", "Europe/London"),
        "user_agent": os.environ.get(
            "GEMINI_SEARCH_USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        ),
    }


def _validate_local_cdp_url(cdp_url: Optional[str]) -> Optional[str]:
    if not cdp_url:
        return None
    parsed = urlparse(cdp_url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("CDP_URL must be an HTTP URL")
    host = (parsed.hostname or "").lower()
    allowed_hosts = {"127.0.0.1", "localhost", "::1"}
    if host not in allowed_hosts:
        raise ValueError("CDP_URL may only point to a local in-container browser")
    return cdp_url


class AIModeEngine:
    """Single-page AI Mode engine with pluggable browser backends."""

    def __init__(self):
        self._playwright = None
        self._playwright_browser = None
        self._playwright_context = None
        self._playwright_page = None
        self._ws = None
        self._ws_url = None
        self._page_target = None
        self._lock = asyncio.Lock()
        self._msg_id = 0
        self._cdp_url = None
        self._user_data_dir = None
        self._owns_user_data_dir = False
        self._browser_backend = "playwright"
        self._headless = True

    async def start(
        self,
        cdp_url=None,
        headless=False,
        channel="chrome",
        user_data_dir: Optional[str] = None,
        browser_backend: Optional[str] = None,
        proxy_server: Optional[str] = None,
    ):
        """Start or connect to a local browser.

        If cdp_url is provided, it must point to a local in-container Chrome instance.
        - playwright: Playwright-controlled browser using a local browser binary.
        - cloakbrowser: optional CloakBrowser wrapper with Playwright-like API.

        user_data_dir can be supplied to persist cookies across runs. When it is
        omitted, profiles/default is used by default.
        """
        user_data_dir = (
            user_data_dir
            or os.environ.get("GEMINI_SEARCH_USER_DATA_DIR")
            or _default_user_data_dir()
        )
        self._cdp_url = _validate_local_cdp_url(cdp_url)
        self._browser_backend = _normalize_browser_backend(
            _env_or_value(browser_backend, "GEMINI_SEARCH_BROWSER_BACKEND")
        )
        self._headless = headless
        try:
            if self._cdp_url:
                await self._connect_cdp(self._cdp_url)
            else:
                await self._launch_browser(
                    headless=headless,
                    channel=channel,
                    user_data_dir=user_data_dir,
                    browser_backend=self._browser_backend,
                    proxy_server=proxy_server,
                )
            await self._warmup()
        except Exception:
            await self.stop()
            raise

    def _prepare_user_data_dir(self, user_data_dir: Optional[str]) -> str:
        if user_data_dir:
            profile_path = Path(user_data_dir).expanduser().resolve()
            profile_path.mkdir(parents=True, exist_ok=True)
            self._user_data_dir = str(profile_path)
            self._owns_user_data_dir = False
        else:
            self._user_data_dir = tempfile.mkdtemp(prefix="gemini-search-mcp-")
            self._owns_user_data_dir = True
        return self._user_data_dir

    async def _launch_browser(
        self,
        headless=True,
        channel="chrome",
        user_data_dir: Optional[str] = None,
        browser_backend: Optional[str] = None,
        proxy_server: Optional[str] = None,
    ):
        backend = _normalize_browser_backend(browser_backend)
        if backend == "playwright":
            await self._launch_playwright_browser(
                headless=headless,
                channel=channel,
                user_data_dir=user_data_dir,
                proxy_server=proxy_server,
            )
            return
        if backend == "cloakbrowser":
            await self._launch_cloakbrowser(
                headless=headless,
                user_data_dir=user_data_dir,
                proxy_server=proxy_server,
            )
            return
        raise ValueError(f"Unsupported browser backend: {backend}")

    async def _launch_playwright_browser(
        self,
        headless=True,
        channel="chrome",
        user_data_dir: Optional[str] = None,
        proxy_server: Optional[str] = None,
    ):
        """Launch a Playwright-controlled browser page."""
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                "playwright backend requires: pip install -e . and playwright install chromium"
            ) from exc

        self._playwright = await async_playwright().start()
        proxy = _env_or_value(proxy_server, "GEMINI_SEARCH_PROXY_SERVER")
        default_args = [
            "--disable-blink-features=AutomationControlled",
            "--enable-gpu",
            "--enable-webgl",
            "--use-gl=angle",
            "--window-size=1365,768",
        ]
        launch_args = default_args + shlex.split(
            os.environ.get("GEMINI_SEARCH_CHROME_EXTRA_ARGS", "")
        )
        launch_options = {
            "headless": headless,
            "args": launch_args,
            "ignore_default_args": ["--enable-automation"],
        }
        if proxy:
            launch_options["proxy"] = {"server": proxy}

        executable_path = _env_or_value(None, "CHROME_PATH")
        if executable_path:
            launch_options["executable_path"] = executable_path
        elif channel in ("chrome", "msedge"):
            launch_options["channel"] = channel

        context_options = _browser_context_options()
        if user_data_dir:
            profile_dir = self._prepare_user_data_dir(user_data_dir)
            self._playwright_context = await self._playwright.chromium.launch_persistent_context(
                profile_dir,
                **context_options,
                **launch_options,
            )
        else:
            self._playwright_browser = await self._playwright.chromium.launch(**launch_options)
            self._playwright_context = await self._playwright_browser.new_context(
                **context_options
            )
        await self._apply_playwright_stealth()
        self._playwright_page = await self._playwright_context.new_page()

    async def _apply_playwright_stealth(self):
        """Apply Python stealth plugin when available, plus local browser shims."""
        try:
            from playwright_stealth import Stealth
        except ImportError:
            await self._playwright_context.add_init_script(_STEALTH_INIT_JS)
            return

        try:
            stealth = Stealth()
            apply = getattr(stealth, "apply_stealth_async", None)
            if apply is not None:
                await apply(self._playwright_context)
                await self._playwright_context.add_init_script(_STEALTH_INIT_JS)
                return
        except TypeError:
            pass

        try:
            from playwright_stealth import stealth_async
        except ImportError:
            await self._playwright_context.add_init_script(_STEALTH_INIT_JS)
            return
        page = await self._playwright_context.new_page()
        try:
            await stealth_async(page)
        finally:
            await page.close()
        await self._playwright_context.add_init_script(_STEALTH_INIT_JS)

    async def _launch_cloakbrowser(
        self,
        headless=True,
        user_data_dir: Optional[str] = None,
        proxy_server: Optional[str] = None,
    ):
        """Launch CloakBrowser through its optional Playwright-compatible wrapper."""
        try:
            import cloakbrowser
        except ImportError as exc:
            raise RuntimeError(
                "cloakbrowser backend requires: pip install -e '.[cloakbrowser]'"
            ) from exc

        proxy = _env_or_value(proxy_server, "GEMINI_SEARCH_PROXY_SERVER")
        kwargs = {"headless": headless}
        if proxy:
            kwargs["proxy"] = {"server": proxy}

        profile_dir = self._prepare_user_data_dir(user_data_dir) if user_data_dir else None
        if profile_dir and hasattr(cloakbrowser, "launch_persistent_context_async"):
            self._playwright_context = await cloakbrowser.launch_persistent_context_async(
                profile_dir,
                **kwargs,
            )
            self._playwright_page = await self._playwright_context.new_page()
            return

        if profile_dir and hasattr(cloakbrowser, "launch_persistent_context"):
            self._playwright_context = await _maybe_await(
                cloakbrowser.launch_persistent_context(profile_dir, **kwargs)
            )
            self._playwright_page = await _maybe_await(self._playwright_context.new_page())
            return

        launcher = getattr(cloakbrowser, "launch_async", None)
        if launcher is None:
            launcher = getattr(cloakbrowser, "launch", None)
        if launcher is None:
            raise RuntimeError("cloakbrowser package does not expose launch_async or launch")

        browser = launcher(**kwargs)
        browser = await _maybe_await(browser)
        self._playwright_browser = browser
        if hasattr(browser, "new_context"):
            self._playwright_context = await _maybe_await(browser.new_context())
            self._playwright_page = await _maybe_await(self._playwright_context.new_page())
        else:
            self._playwright_page = await _maybe_await(browser.new_page())

    async def _wait_for_cdp(self, port: int, label: str, timeout_sec: float = 20.0):
        """Wait until Chrome exposes /json/version on the requested CDP port."""
        import urllib.request

        last_error = None
        attempts = max(1, int(timeout_sec * 2))
        for _ in range(attempts):
            await asyncio.sleep(0.5)
            try:
                data = urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/json/version", timeout=2
                ).read()
                info = json.loads(data)
                self._ws_url = info["webSocketDebuggerUrl"]
                return
            except Exception as exc:  # noqa: BLE001 - diagnostic retry loop
                last_error = exc
        raise RuntimeError(f"{label} did not expose CDP on port {port}: {last_error}")

    async def _connect_cdp(self, http_url):
        """Connect to Chrome via CDP WebSocket."""
        import urllib.request

        try:
            data = urllib.request.urlopen(f"{http_url}/json/version", timeout=5).read()
            info = json.loads(data)
            self._ws_url = info["webSocketDebuggerUrl"]
        except Exception as e:
            raise RuntimeError(f"Cannot connect to Chrome at {http_url}: {e}")

        pages = json.loads(urllib.request.urlopen(f"{http_url}/json/list", timeout=5).read())
        page_targets = [p for p in pages if p.get("type") == "page"]
        if page_targets:
            self._page_target = page_targets[0]["webSocketDebuggerUrl"]
        else:
            new_tab = json.loads(urllib.request.urlopen(f"{http_url}/json/new?about:blank", timeout=5).read())
            self._page_target = new_tab["webSocketDebuggerUrl"]

        if not websockets:
            raise RuntimeError("websockets package required: pip install websockets")
        self._ws = await websockets.connect(self._page_target, max_size=10 * 1024 * 1024)

    async def _cdp_send(self, method, params=None):
        """Send a CDP command and return the result."""
        self._msg_id += 1
        msg = {"id": self._msg_id, "method": method, "params": params or {}}
        await self._ws.send(json.dumps(msg))
        while True:
            resp = json.loads(await self._ws.recv())
            if resp.get("id") == self._msg_id:
                if "error" in resp:
                    raise RuntimeError(f"CDP error: {resp['error']}")
                return resp.get("result", {})

    async def _evaluate(self, expression):
        """Evaluate JS in the page and return the result."""
        if self._playwright_page is not None:
            return await self._playwright_page.evaluate(expression)

        result = await self._cdp_send("Runtime.evaluate", {
            "expression": expression,
            "awaitPromise": True,
            "returnByValue": True,
        })
        val = result.get("result", {}).get("value")
        exc = result.get("exceptionDetails")
        if exc:
            desc = exc.get("exception", {}).get("description", exc.get("text", str(exc)))
            raise RuntimeError(f"JS error: {desc}")
        return val

    async def _navigate(self, url):
        """Navigate the page to a URL and wait for load."""
        if self._playwright_page is not None:
            await self._playwright_page.goto(url, wait_until="load")
            await asyncio.sleep(1)
            return

        await self._cdp_send("Page.enable")
        await self._cdp_send("Page.navigate", {"url": url})
        for _ in range(60):
            msg = json.loads(await self._ws.recv())
            if msg.get("method") == "Page.loadEventFired":
                break
        await asyncio.sleep(1)

    async def _warmup(self):
        """Navigate to Google search to build cookie session."""
        if self._playwright_page is not None:
            await self._human_warmup_playwright()
        else:
            query = quote(_warmup_query(), safe="")
            await self._navigate(f"{_google_base_url()}/search?q={query}&hl=en-GB&gl=GB")
        if await self._captcha_visible():
            if not self._headless:
                await self._wait_for_manual_captcha()
                return
            raise RuntimeError(
                "Google CAPTCHA during warmup. Try a visible persistent profile "
                "or an existing browser via --cdp-url."
            )

    async def _captcha_visible(self) -> bool:
        """Best-effort CAPTCHA/sorry-page detection during navigation churn."""
        for _ in range(5):
            try:
                if self._playwright_page is not None:
                    url = self._playwright_page.url or ""
                    title = await self._playwright_page.title()
                    body = await self._playwright_page.locator("body").inner_text(timeout=1500)
                else:
                    url = await self._evaluate("window.location.href")
                    title = ""
                    body = ""
                text = f"{url}\n{title}\n{body}".lower()
                if any(
                    marker in text
                    for marker in (
                        "/sorry/",
                        "captcha",
                        "unusual traffic",
                        "not a robot",
                        "our systems have detected",
                    )
                ):
                    return True
                return False
            except Exception:
                await asyncio.sleep(1)
        return False

    async def _wait_for_manual_captcha(self):
        """Wait for a user to solve Google CAPTCHA in a visible browser."""
        timeout_sec = _env_int("GEMINI_SEARCH_MANUAL_CAPTCHA_TIMEOUT", 600)
        print(
            "Google CAPTCHA detected. Complete it in the browser window; "
            f"waiting up to {timeout_sec} seconds..."
        )
        deadline = asyncio.get_running_loop().time() + timeout_sec
        poll_sec = _env_int("GEMINI_SEARCH_MANUAL_CAPTCHA_POLL_SECONDS", 10)
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(poll_sec)
            if not await self._captcha_visible():
                await asyncio.sleep(random.uniform(1.0, 2.0))
                return
        raise RuntimeError("Google CAPTCHA was not completed before the manual timeout")

    async def wait_for_manual_inspection(self, reason: str):
        """Keep a visible browser open so a user can inspect or solve CAPTCHA."""
        if self._headless:
            return
        timeout_sec = _env_int("GEMINI_SEARCH_MANUAL_CAPTCHA_TIMEOUT", 600)
        print(f"{reason} Keeping browser open for up to {timeout_sec} seconds...")
        await asyncio.sleep(timeout_sec)

    async def _human_warmup_playwright(self):
        """Build an initial Google session through visible page interactions."""
        page = self._playwright_page
        base_url = _google_base_url()
        warmup_query = _warmup_query()
        await page.goto(f"{base_url}/?hl=en-GB&gl=GB", wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(1.5, 3.5))

        consent_patterns = [
            "Accept all",
            "I agree",
            "Agree",
            "Reject all",
            "Stay signed out",
        ]
        for text in consent_patterns:
            try:
                button = page.get_by_role("button", name=text)
                if await button.count():
                    await button.first.click(delay=random.randint(80, 180), timeout=1500)
                    await asyncio.sleep(random.uniform(0.8, 1.8))
                    break
            except Exception:
                pass

        search_box = page.locator("textarea[name='q'], input[name='q']").first
        try:
            await search_box.wait_for(state="visible", timeout=5000)
            await search_box.click(delay=random.randint(60, 160))
            await asyncio.sleep(random.uniform(0.3, 0.9))
            for char in warmup_query:
                await page.keyboard.type(char, delay=random.randint(80, 220))
            await asyncio.sleep(random.uniform(0.4, 1.2))
            await page.keyboard.press("Enter")
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
            await asyncio.sleep(random.uniform(1.5, 3.5))
        except Exception:
            query = quote(warmup_query, safe="")
            await self._navigate(f"{base_url}/search?q={query}&hl=en-GB&gl=GB")

    async def browser_fingerprint(self) -> dict:
        """Return a small browser fingerprint sample for diagnostics."""
        return await self._evaluate(
            """
            (() => ({
                webdriver: navigator.webdriver,
                plugins: navigator.plugins ? navigator.plugins.length : 0,
                mimeTypes: navigator.mimeTypes ? navigator.mimeTypes.length : 0,
                languages: navigator.languages,
                platform: navigator.platform,
                hardwareConcurrency: navigator.hardwareConcurrency,
                deviceMemory: navigator.deviceMemory,
                screen: {
                    width: screen.width,
                    height: screen.height,
                    availWidth: screen.availWidth,
                    availHeight: screen.availHeight,
                },
                viewport: {
                    width: window.innerWidth,
                    height: window.innerHeight,
                    deviceScaleFactor: window.devicePixelRatio,
                },
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                locale: Intl.DateTimeFormat().resolvedOptions().locale,
                webglVendor: (() => {
                    const canvas = document.createElement('canvas');
                    const gl = canvas.getContext('webgl');
                    if (!gl) return null;
                    const ext = gl.getExtension('WEBGL_debug_renderer_info');
                    return ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : null;
                })(),
                webglRenderer: (() => {
                    const canvas = document.createElement('canvas');
                    const gl = canvas.getContext('webgl');
                    if (!gl) return null;
                    const ext = gl.getExtension('WEBGL_debug_renderer_info');
                    return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : null;
                })(),
            }))()
            """
        )

    async def ask(self, question: str, timeout_ms: int = 45000) -> str:
        """Ask a question via Google AI Mode."""
        async with self._lock:
            base_url = _google_base_url()
            js = (
                _ASK_JS
                .replace("%SEARCH_URL%", json.dumps(f"{base_url}/search"))
                .replace("%ASYNC_URL%", json.dumps(f"{base_url}/async/folwr"))
                .replace("%QUERY%", json.dumps(question))
            )
            try:
                result = await asyncio.wait_for(self._evaluate(js), timeout=timeout_ms / 1000)
            except asyncio.TimeoutError:
                raise RuntimeError("Query timed out")
            except Exception:
                await self._warmup()
                result = await self._evaluate(js)

        if isinstance(result, dict):
            if result.get("error"):
                raise RuntimeError(f"{result['error']}: {result.get('message','')}")
            return result.get("answer", "")
        return str(result) if result else ""

    async def ask_stream(self, question: str, timeout_ms: int = 45000):
        """Yield answer in one chunk."""
        text = await self.ask(question, timeout_ms)
        if text:
            yield text

    async def stop(self):
        """Shutdown browser resources and remove owned temporary profile."""
        if self._ws:
            await self._ws.close()
            self._ws = None
        if self._playwright_context:
            try:
                await self._playwright_context.close()
            except Exception:
                pass
            self._playwright_context = None
        if self._playwright_browser:
            try:
                await self._playwright_browser.close()
            except Exception:
                pass
            self._playwright_browser = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        self._playwright_page = None
        if self._user_data_dir:
            if self._owns_user_data_dir:
                shutil.rmtree(self._user_data_dir, ignore_errors=True)
            self._user_data_dir = None
            self._owns_user_data_dir = False


async def e2e_test():
    import time

    cdp = os.environ.get("CDP_URL")
    channel = os.environ.get("BROWSER_CHANNEL", "chrome")
    headless = os.environ.get("HEADLESS", "0") != "0"
    browser_backend = os.environ.get("GEMINI_SEARCH_BROWSER_BACKEND")
    user_data_dir = os.environ.get("GEMINI_SEARCH_USER_DATA_DIR")
    proxy_server = os.environ.get("GEMINI_SEARCH_PROXY_SERVER")
    engine = AIModeEngine()
    print(
        "Starting... "
        f"(cdp={cdp or 'self-launch'}, backend={browser_backend or 'playwright'}, "
        f"channel={channel}, headless={headless})"
    )
    t0 = time.time()
    await engine.start(
        cdp_url=cdp,
        headless=headless,
        channel=channel,
        user_data_dir=user_data_dir,
        browser_backend=browser_backend,
        proxy_server=proxy_server,
    )
    print(f"  Ready in {time.time()-t0:.1f}s")
    try:
        fingerprint = await engine.browser_fingerprint()
        print(f"  Fingerprint: {json.dumps(fingerprint, ensure_ascii=False)}")
    except Exception as exc:
        print(f"  Fingerprint check failed: {exc}")

    tests = [
        ("math", "what is 7*8? answer only the number"),
        ("web", "what is the current bitcoin price in USD today?"),
        ("chinese", "用中文简要介绍量子计算, 不超过2句话"),
    ]
    passed = 0
    failures = 0
    for name, q in tests:
        t0 = time.time()
        try:
            ans = await engine.ask(q)
            print(f"  [{name}] ({time.time()-t0:.1f}s): {ans[:120]}")
            if ans:
                passed += 1
        except Exception as e:
            failures += 1
            print(f"  [{name}] ERROR: {e}")

    if failures and not headless:
        await engine.wait_for_manual_inspection(
            "One or more tests failed. Complete CAPTCHA or inspect the browser window."
        )

    await engine.stop()
    print(f"\n{'PASSED' if passed == len(tests) else 'PARTIAL'} ({passed}/{len(tests)})")


if __name__ == "__main__":
    asyncio.run(e2e_test())
