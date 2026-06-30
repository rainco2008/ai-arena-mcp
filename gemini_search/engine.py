"""Lightweight engine for Google AI Mode."""
from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import shutil
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

try:
    import websockets
except ImportError:  # pragma: no cover - surfaced at runtime by _connect_cdp
    websockets = None


_ASK_JS = """
(async (q) => {
    try {
        const pageUrl = 'https://www.google.com.hk/search?q=' + encodeURIComponent(q) + '&hl=en&gl=us&udm=50&aep=1&ntc=1';
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
        const p = new URLSearchParams({srtst,garc,mlro:lro,mlros,ei,q,yv:'3',vet:'1'+ved+'..i',ved,aep:'1',gl:'us',hl:'en',sca_esv:sca,udm:'50',stkp,cs:'0',async:'_fmt:adl,_xsrf:'+xsrf});
        const r2 = await fetch('https://www.google.com.hk/async/folwr?'+p.toString(), {credentials:'include'});
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
        "http": "request",
        "requests": "request",
        "request": "request",
        "playwright": "playwright",
        "pw": "playwright",
        "cloak": "cloakbrowser",
        "cloakbrowser": "cloakbrowser",
    }
    if value not in aliases:
        raise ValueError(
            "browser_backend must be one of: request, playwright, cloakbrowser"
        )
    return aliases[value]


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
        self._http_client = None
        self._ws = None
        self._ws_url = None
        self._page_target = None
        self._lock = asyncio.Lock()
        self._msg_id = 0
        self._cdp_url = None
        self._user_data_dir = None
        self._owns_user_data_dir = False
        self._browser_backend = "playwright"

    async def start(
        self,
        cdp_url=None,
        headless=True,
        channel="chrome",
        user_data_dir: Optional[str] = None,
        browser_backend: Optional[str] = None,
        proxy_server: Optional[str] = None,
    ):
        """Start or connect to a local browser.

        If cdp_url is provided, it must point to a local in-container Chrome instance.
        - request: direct HTTP requests without a browser.
        - playwright: Playwright-controlled browser using a local browser binary.
        - cloakbrowser: optional CloakBrowser wrapper with Playwright-like API.

        user_data_dir can be supplied to persist cookies across runs. When it is
        omitted, a temporary profile is created and deleted on stop.
        """
        self._cdp_url = _validate_local_cdp_url(cdp_url)
        self._browser_backend = _normalize_browser_backend(
            _env_or_value(browser_backend, "GEMINI_SEARCH_BROWSER_BACKEND")
        )
        try:
            if self._browser_backend == "request":
                await self._start_request_backend()
            elif self._cdp_url:
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

    async def _start_request_backend(self):
        """Start direct HTTP backend without browser automation."""
        self._http_client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(30.0),
            headers={
                "User-Agent": os.environ.get(
                    "GEMINI_SEARCH_USER_AGENT",
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
        )

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
        launch_args = shlex.split(os.environ.get("GEMINI_SEARCH_CHROME_EXTRA_ARGS", ""))
        launch_options = {
            "headless": headless,
            "args": launch_args,
        }
        if proxy:
            launch_options["proxy"] = {"server": proxy}

        executable_path = _env_or_value(None, "CHROME_PATH")
        if executable_path:
            launch_options["executable_path"] = executable_path
        elif channel in ("chrome", "msedge"):
            launch_options["channel"] = channel

        if user_data_dir:
            profile_dir = self._prepare_user_data_dir(user_data_dir)
            self._playwright_context = await self._playwright.chromium.launch_persistent_context(
                profile_dir,
                **launch_options,
            )
        else:
            self._playwright_browser = await self._playwright.chromium.launch(**launch_options)
            self._playwright_context = await self._playwright_browser.new_context()
        self._playwright_page = await self._playwright_context.new_page()

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
        if self._browser_backend == "request":
            return
        await self._navigate("https://www.google.com.hk/search?q=hello&hl=en&gl=us")
        url = await self._evaluate("window.location.href")
        if "/sorry/" in (url or ""):
            raise RuntimeError(
                "Google CAPTCHA during warmup. Try a visible persistent profile "
                "or an existing browser via --cdp-url."
            )

    async def ask(self, question: str, timeout_ms: int = 45000) -> str:
        """Ask a question via Google AI Mode."""
        if self._browser_backend == "request":
            return await self._ask_request(question, timeout_ms)

        async with self._lock:
            js = _ASK_JS.replace("%QUERY%", json.dumps(question))
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

    async def _ask_request(self, question: str, timeout_ms: int = 45000) -> str:
        """Ask through direct HTTP requests. This is simpler but less resilient."""
        if self._http_client is None:
            await self._start_request_backend()

        params = {"q": question, "hl": "en", "gl": "us", "udm": "50", "aep": "1", "ntc": "1"}
        r1 = await asyncio.wait_for(
            self._http_client.get("https://www.google.com.hk/search", params=params),
            timeout=timeout_ms / 1000,
        )
        r1.raise_for_status()
        html = r1.text

        def match(pattern: str) -> str:
            found = re.search(pattern, html)
            return found.group(1) if found else ""

        srtst = match(r'data-srtst="([^"]+)"')
        if not srtst:
            raise RuntimeError("request backend could not extract AI Mode token")

        query = {
            "srtst": srtst,
            "garc": match(r'data-garc="([^"]+)"'),
            "mlro": match(r'data-lro-token="([^"]+)"'),
            "mlros": match(r'data-lro-signature="([^"]+)"'),
            "ei": match(r'data-ei="([^"]+)"'),
            "q": question,
            "yv": "3",
            "vet": "1" + match(r'aria-current="page"[^>]*data-ved="([^"]+)"') + "..i",
            "ved": match(r'aria-current="page"[^>]*data-ved="([^"]+)"'),
            "aep": "1",
            "gl": "us",
            "hl": "en",
            "sca_esv": match(r"sca_esv=([a-f0-9]+)"),
            "udm": "50",
            "stkp": match(r'data-stkp="([^"]+)"'),
            "cs": "0",
            "async": "_fmt:adl,_xsrf:" + match(r'data-xsrf-folwr-token="([^"]+)"'),
        }
        r2 = await self._http_client.get("https://www.google.com.hk/async/folwr", params=query)
        r2.raise_for_status()
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", r2.text, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

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
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        if self._user_data_dir:
            if self._owns_user_data_dir:
                shutil.rmtree(self._user_data_dir, ignore_errors=True)
            self._user_data_dir = None
            self._owns_user_data_dir = False


async def e2e_test():
    import time

    cdp = os.environ.get("CDP_URL")
    channel = os.environ.get("BROWSER_CHANNEL", "chrome")
    headless = os.environ.get("HEADLESS", "1") != "0"
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

    tests = [
        ("math", "what is 7*8? answer only the number"),
        ("web", "what is the current bitcoin price in USD today?"),
        ("chinese", "用中文简要介绍量子计算, 不超过2句话"),
    ]
    passed = 0
    for name, q in tests:
        t0 = time.time()
        try:
            ans = await engine.ask(q)
            print(f"  [{name}] ({time.time()-t0:.1f}s): {ans[:120]}")
            if ans:
                passed += 1
        except Exception as e:
            print(f"  [{name}] ERROR: {e}")

    await engine.stop()
    print(f"\n{'PASSED' if passed == len(tests) else 'PARTIAL'} ({passed}/{len(tests)})")


if __name__ == "__main__":
    asyncio.run(e2e_test())
