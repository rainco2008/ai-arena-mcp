"""Search and scraping provider router backed by Scrapling and search APIs."""
from __future__ import annotations

import asyncio
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote_plus, urlencode, urljoin

from .web_chat import WebChatProvider, normalize_web_chat_provider


MASKED_VALUE = "********"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def mask_secret(value: Optional[str]) -> str:
    return MASKED_VALUE if value else ""


def merge_secret(current: Optional[str], incoming: Optional[str]) -> Optional[str]:
    if incoming is None or incoming == "":
        return current
    if incoming == MASKED_VALUE:
        return current
    return incoming


def normalize_search_provider(provider: Optional[str]) -> str:
    value = (provider or "scrapling").strip().lower()
    aliases = {
        "scrapling": "scrapling",
        "html": "scrapling",
        "duckduckgo": "scrapling",
        "gemini": "gemini_grounding",
        "gemini_grounding": "gemini_grounding",
        "google_search_grounding": "gemini_grounding",
        "brave": "brave",
        "tavily": "tavily",
    }
    if value not in aliases:
        raise ValueError(
            "search_provider must be one of: scrapling, gemini_grounding, brave, tavily"
        )
    return aliases[value]


def normalize_scrape_backend(backend: Optional[str]) -> str:
    value = (backend or "scrapling").strip().lower()
    aliases = {
        "scrapling": "scrapling",
        "static": "scrapling",
        "fetcher": "scrapling",
        "scrapling_chromium": "scrapling_chromium",
        "chromium": "scrapling_chromium",
        "dynamic": "scrapling_chromium",
        "scrapling_stealthy": "scrapling_stealthy",
        "stealthy": "scrapling_stealthy",
        "cloak": "cloakbrowser",
        "cloakbrowser": "cloakbrowser",
    }
    if value not in aliases:
        raise ValueError(
            "scrape_backend must be one of: scrapling, scrapling_chromium, scrapling_stealthy, cloakbrowser"
        )
    return aliases[value]


def _http_json(url: str, payload: Optional[dict] = None, headers: Optional[dict] = None, timeout: int = 45) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if payload is not None else {}),
            **(headers or {}),
        },
        method="POST" if payload is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body[:800]}") from exc
    return json.loads(body) if body else {}


def _clean_text(value: str, limit: int = 8000) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    return text[:limit].rstrip()


def _first_text(node, selectors: list[str]) -> str:
    for selector in selectors:
        try:
            value = node.css(selector).get()
        except Exception:
            value = None
        if value:
            return _clean_text(str(value), 500)
    return ""


def _all_text(page, selectors: list[str]) -> str:
    parts: list[str] = []
    for selector in selectors:
        try:
            values = page.css(selector).getall()
        except Exception:
            values = []
        for value in values:
            cleaned = _clean_text(str(value), 1000)
            if cleaned:
                parts.append(cleaned)
    return "\n\n".join(parts)


async def _maybe_await(value):
    if hasattr(value, "__await__"):
        return await value
    return value


@dataclass
class ScrapedPage:
    url: str
    title: str
    text: str


class SearchEngine:
    """Routes search and scraping calls to Scrapling or API-backed providers."""

    def __init__(self):
        self._config: dict = {}
        self._lock = asyncio.Lock()
        self._web_chat = WebChatProvider()

    @property
    def provider(self) -> str:
        return normalize_search_provider(self._config.get("search_provider"))

    async def start(self, **config):
        self._config = dict(config)
        self._validate_api_provider()
        await self._web_chat.start(**config)

    async def stop(self):
        await self._web_chat.stop()

    async def ask(self, question: str, timeout_ms: int = 45000) -> str:
        async with self._lock:
            provider = self.provider
            timeout = max(1, int(timeout_ms / 1000))
            if provider == "scrapling":
                return await asyncio.to_thread(self._ask_scrapling, question, timeout)
            if provider == "gemini_grounding":
                return await asyncio.to_thread(self._ask_gemini_grounding, question, timeout)
            if provider == "brave":
                return await asyncio.to_thread(self._ask_brave, question, timeout)
            if provider == "tavily":
                return await asyncio.to_thread(self._ask_tavily, question, timeout)
            raise RuntimeError(f"Unsupported search provider: {provider}")

    async def ask_stream(self, question: str, timeout_ms: int = 45000):
        text = await self.ask(question, timeout_ms)
        if text:
            yield text

    async def chat(self, prompt: str, timeout_ms: int = 120000) -> str:
        provider = normalize_web_chat_provider(self._config.get("web_chat_provider"))
        if provider == "disabled":
            return await self.ask(prompt, timeout_ms=timeout_ms)
        return await self._web_chat.ask(prompt, timeout_ms=timeout_ms)

    async def chat_stream(self, prompt: str, timeout_ms: int = 120000):
        text = await self.chat(prompt, timeout_ms)
        if text:
            yield text

    async def scrape(self, url: str, selector: Optional[str] = None, timeout_ms: int = 45000) -> str:
        timeout = max(1, int(timeout_ms / 1000))
        backend = normalize_scrape_backend(self._config.get("scrape_backend"))
        if backend == "cloakbrowser":
            page = await self._scrape_url_cloakbrowser(url, selector, timeout)
        else:
            page = await asyncio.to_thread(self._scrape_url, url, selector, timeout, backend)
        lines = [f"URL: {page.url}"]
        if page.title:
            lines.append(f"Title: {page.title}")
        lines.append("")
        lines.append(page.text or "(no readable text found)")
        return "\n".join(lines)

    def _validate_api_provider(self):
        provider = self.provider
        if provider == "gemini_grounding" and not self._gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required for gemini_grounding")
        if provider == "brave" and not self._brave_api_key:
            raise RuntimeError("BRAVE_API_KEY is required for brave")
        if provider == "tavily" and not self._tavily_api_key:
            raise RuntimeError("TAVILY_API_KEY is required for tavily")

    @property
    def _gemini_api_key(self) -> Optional[str]:
        return self._config.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY")

    @property
    def _brave_api_key(self) -> Optional[str]:
        return self._config.get("brave_api_key") or os.environ.get("BRAVE_API_KEY")

    @property
    def _tavily_api_key(self) -> Optional[str]:
        return self._config.get("tavily_api_key") or os.environ.get("TAVILY_API_KEY")

    def _scrapling_fetcher(self, backend: str = "scrapling"):
        try:
            from scrapling.fetchers import DynamicFetcher, Fetcher, StealthyFetcher
        except ImportError as exc:
            raise RuntimeError(
                'Scrapling fetchers are required. Install with: pip install "scrapling[all]"'
            ) from exc
        if backend == "scrapling_chromium":
            return DynamicFetcher
        if backend == "scrapling_stealthy":
            return StealthyFetcher
        return Fetcher

    def _fetch_with_scrapling(self, url: str, timeout: int, backend: str):
        Fetcher = self._scrapling_fetcher(backend)
        kwargs = {
            "timeout": timeout,
            "headers": {"User-Agent": DEFAULT_USER_AGENT},
        }
        proxy = self._config.get("proxy_server") or os.environ.get("GEMINI_SEARCH_PROXY_SERVER")
        if proxy:
            kwargs["proxy"] = proxy
        if backend in ("scrapling_chromium", "scrapling_stealthy"):
            kwargs["headless"] = bool(self._config.get("headless", True))
            kwargs["network_idle"] = True
            fetch = getattr(Fetcher, "fetch", None)
            if fetch is None:
                raise RuntimeError(f"{backend} does not expose fetch()")
            return fetch(url, **kwargs)
        return Fetcher.get(url, **kwargs)

    def _scrape_url(self, url: str, selector: Optional[str], timeout: int, backend: str) -> ScrapedPage:
        page = self._fetch_with_scrapling(url, timeout, backend)
        title = _first_text(page, ["title::text", "h1::text"])
        if selector:
            text = _all_text(page, [selector])
        else:
            text = _all_text(page, [
                "main ::text",
                "article ::text",
                "body ::text",
            ])
        return ScrapedPage(url=str(getattr(page, "url", url) or url), title=title, text=_clean_text(text))

    async def _scrape_url_cloakbrowser(self, url: str, selector: Optional[str], timeout: int) -> ScrapedPage:
        try:
            import cloakbrowser
        except ImportError as exc:
            raise RuntimeError(
                'CloakBrowser backend requires: pip install -e ".[cloakbrowser]"'
            ) from exc

        kwargs = {
            "headless": bool(self._config.get("headless", True)),
        }
        proxy = self._config.get("proxy_server") or os.environ.get("GEMINI_SEARCH_PROXY_SERVER")
        if proxy:
            kwargs["proxy"] = proxy

        browser = None
        context = None
        page = None
        try:
            launcher = getattr(cloakbrowser, "launch_async", None) or getattr(cloakbrowser, "launch", None)
            if launcher is None:
                raise RuntimeError("cloakbrowser package does not expose launch_async or launch")
            browser = await _maybe_await(launcher(**kwargs))
            if hasattr(browser, "new_context"):
                context = await _maybe_await(browser.new_context())
                page = await _maybe_await(context.new_page())
            else:
                page = await _maybe_await(browser.new_page())
            await _maybe_await(page.goto(url, wait_until="load", timeout=timeout * 1000))
            title = await _maybe_await(page.title())
            if selector:
                text = await _maybe_await(page.locator(selector).inner_text(timeout=timeout * 1000))
            else:
                text = await _maybe_await(page.locator("body").inner_text(timeout=timeout * 1000))
            return ScrapedPage(url=str(getattr(page, "url", url) or url), title=_clean_text(title, 500), text=_clean_text(text))
        finally:
            for resource in (context, browser):
                if resource and hasattr(resource, "close"):
                    try:
                        await _maybe_await(resource.close())
                    except Exception:
                        pass

    def _ask_scrapling(self, question: str, timeout: int) -> str:
        search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(question)}"
        backend = normalize_scrape_backend(self._config.get("scrape_backend"))
        if backend == "cloakbrowser":
            backend = "scrapling"
        page = self._scrape_url(search_url, ".result", timeout, backend)
        try:
            result_nodes = self._fetch_with_scrapling(search_url, timeout, backend).css(".result")
        except Exception:
            result_nodes = []

        results: list[str] = []
        for node in list(result_nodes)[:8]:
            title = _first_text(node, [".result__title ::text", "a::text"])
            href = ""
            try:
                href = str(node.css(".result__a::attr(href)").get() or "")
            except Exception:
                href = ""
            snippet = _first_text(node, [".result__snippet ::text", ".result__body ::text"])
            if title or href or snippet:
                absolute = urljoin(search_url, href) if href else ""
                results.append(f"- {title or absolute}\n  {absolute}\n  {snippet}".rstrip())

        if results:
            return "Search results:\n" + "\n\n".join(results)
        if page.text:
            return "Search results:\n" + page.text
        raise RuntimeError("Scrapling search returned no usable results")

    def _ask_gemini_grounding(self, question: str, timeout: int) -> str:
        model = self._config.get("gemini_model") or os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash"
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={self._gemini_api_key}"
        )
        data = _http_json(
            url,
            {
                "contents": [{"parts": [{"text": question}]}],
                "tools": [{"google_search": {}}],
            },
            timeout=timeout,
        )
        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError(f"Gemini returned no candidates: {json.dumps(data)[:800]}")
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts).strip()
        grounding = candidates[0].get("groundingMetadata") or {}
        chunks = grounding.get("groundingChunks") or []
        links = []
        for chunk in chunks:
            web = chunk.get("web") or {}
            title = web.get("title")
            uri = web.get("uri")
            if uri:
                links.append(f"- {title or uri}: {uri}")
        if links:
            text = f"{text}\n\nSources:\n" + "\n".join(links[:10])
        return text

    def _ask_brave(self, question: str, timeout: int) -> str:
        params = urlencode({
            "q": question,
            "count": "8",
            "text_decorations": "false",
            "extra_snippets": "true",
        })
        data = _http_json(
            f"https://api.search.brave.com/res/v1/web/search?{params}",
            headers={
                "X-Subscription-Token": self._brave_api_key or "",
                "Accept-Encoding": "identity",
            },
            timeout=timeout,
        )
        answer = data.get("answer") or data.get("infobox", {}).get("long_desc") or ""
        results = (data.get("web") or {}).get("results") or []
        lines = [answer.strip()] if answer else []
        if results:
            lines.append("Search results:")
            for item in results[:8]:
                title = item.get("title") or item.get("url") or "Untitled"
                url = item.get("url") or ""
                desc = item.get("description") or ""
                snippets = " ".join(item.get("extra_snippets") or [])
                summary = " ".join(part for part in (desc, snippets) if part).strip()
                lines.append(f"- {title}\n  {url}\n  {summary}")
        if not lines:
            raise RuntimeError(f"Brave returned no usable results: {json.dumps(data)[:800]}")
        return "\n\n".join(lines)

    def _ask_tavily(self, question: str, timeout: int) -> str:
        data = _http_json(
            "https://api.tavily.com/search",
            {
                "api_key": self._tavily_api_key,
                "query": question,
                "search_depth": self._config.get("tavily_search_depth") or "basic",
                "include_answer": True,
                "include_raw_content": False,
                "max_results": 8,
            },
            timeout=timeout,
        )
        lines = [data.get("answer", "").strip()] if data.get("answer") else []
        results = data.get("results") or []
        if results:
            lines.append("Search results:")
            for item in results[:8]:
                title = item.get("title") or item.get("url") or "Untitled"
                url = item.get("url") or ""
                content = item.get("content") or ""
                lines.append(f"- {title}\n  {url}\n  {content}")
        if not lines:
            raise RuntimeError(f"Tavily returned no usable results: {json.dumps(data)[:800]}")
        return "\n\n".join(lines)
