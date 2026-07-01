"""Search provider router for API-backed and browser-backed engines."""
from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from typing import Optional

from .engine import AIModeEngine


MASKED_VALUE = "********"


def mask_secret(value: Optional[str]) -> str:
    return MASKED_VALUE if value else ""


def merge_secret(current: Optional[str], incoming: Optional[str]) -> Optional[str]:
    if incoming is None or incoming == "":
        return current
    if incoming == MASKED_VALUE:
        return current
    return incoming


def normalize_search_provider(provider: Optional[str]) -> str:
    value = (provider or "google_ai_mode").strip().lower()
    aliases = {
        "google": "google_ai_mode",
        "google_ai_mode": "google_ai_mode",
        "playwright": "google_ai_mode",
        "gemini": "gemini_grounding",
        "gemini_grounding": "gemini_grounding",
        "google_search_grounding": "gemini_grounding",
        "brave": "brave",
        "tavily": "tavily",
    }
    if value not in aliases:
        raise ValueError(
            "search_provider must be one of: google_ai_mode, gemini_grounding, brave, tavily"
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


class SearchEngine:
    """Routes ask() calls to a configured search provider."""

    def __init__(self):
        self._browser_engine: Optional[AIModeEngine] = None
        self._config: dict = {}
        self._lock = asyncio.Lock()

    @property
    def provider(self) -> str:
        return normalize_search_provider(self._config.get("search_provider"))

    async def start(self, **config):
        self._config = dict(config)
        provider = self.provider
        if provider == "google_ai_mode":
            self._browser_engine = AIModeEngine()
            await self._browser_engine.start(
                cdp_url=config.get("cdp_url"),
                headless=config["headless"],
                channel=config["channel"],
                user_data_dir=config.get("user_data_dir"),
                browser_backend=config.get("browser_backend"),
                proxy_server=config.get("proxy_server"),
            )
            return
        self._browser_engine = None
        self._validate_api_provider()

    async def stop(self):
        if self._browser_engine is not None:
            await self._browser_engine.stop()
            self._browser_engine = None

    async def ask(self, question: str, timeout_ms: int = 45000) -> str:
        async with self._lock:
            provider = self.provider
            if provider == "google_ai_mode":
                if self._browser_engine is None:
                    raise RuntimeError("Google AI Mode browser engine is not ready")
                return await self._browser_engine.ask(question, timeout_ms=timeout_ms)
            timeout = max(1, int(timeout_ms / 1000))
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
        from urllib.parse import urlencode

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
