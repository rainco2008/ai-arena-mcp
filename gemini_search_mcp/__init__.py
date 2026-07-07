"""Search and scraping MCP server for AI agents."""
import asyncio
from typing import Optional
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from gemini_search.providers import SearchEngine

mcp = FastMCP(name="ContentPilot")
READONLY = ToolAnnotations(readOnlyHint=True)

_engine: Optional[SearchEngine] = None
_lock = asyncio.Lock()


async def _get_engine() -> SearchEngine:
    global _engine
    if _engine is None:
        async with _lock:
            if _engine is None:
                import os
                _engine = SearchEngine()
                proxy_server = os.environ.get("GEMINI_SEARCH_PROXY_SERVER")
                await _engine.start(
                    headless=os.environ.get("HEADLESS", "1") != "0",
                    scrape_backend=os.environ.get("GEMINI_SEARCH_SCRAPE_BACKEND", "scrapling"),
                    proxy_server=proxy_server,
                    search_provider=os.environ.get("GEMINI_SEARCH_PROVIDER", "scrapling"),
                    web_chat_provider=os.environ.get("WEB_CHAT_PROVIDER", "disabled"),
                    web_chat_backend=os.environ.get("WEB_CHAT_BACKEND", "playwright"),
                    web_chat_headless=os.environ.get("WEB_CHAT_HEADLESS", "0") != "0",
                    web_chat_profile_dir=os.environ.get("WEB_CHAT_PROFILE_DIR"),
                    gemini_api_key=os.environ.get("GEMINI_API_KEY"),
                    gemini_model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
                    brave_api_key=os.environ.get("BRAVE_API_KEY"),
                    tavily_api_key=os.environ.get("TAVILY_API_KEY"),
                    tavily_search_depth=os.environ.get("TAVILY_SEARCH_DEPTH", "basic"),
                )
    return _engine


@mcp.tool(annotations=READONLY)
async def web_search(
    query: str,
) -> str:
    """Search the web and return current results.

    Args:
        query: Search query or question.
               Examples: "latest news about AI regulation", "Bitcoin price today",
               "how does mRNA vaccine work", "Python asyncio best practices 2026"

    Returns:
        Current search results or an API-grounded answer depending on configuration.
    """
    engine = await _get_engine()
    return await engine.ask(query)


@mcp.tool(annotations=READONLY)
async def ask(
    prompt: str,
) -> str:
    """Ask the configured web chat provider, or fall back to search.

    Args:
        prompt: Any question for the configured model website.

    Returns:
        The latest model answer from the website, or search results when web chat is disabled.
    """
    engine = await _get_engine()
    return await engine.chat(prompt)


@mcp.tool(annotations=READONLY)
async def scrape_url(
    url: str,
    selector: str = "",
    timeout_ms: int = 45000,
) -> str:
    """Fetch a web page with Scrapling and return readable text.

    Args:
        url: HTTP or HTTPS URL to fetch.
        selector: Optional CSS selector. When omitted, main/article/body text is returned.
        timeout_ms: Fetch timeout in milliseconds.

    Returns:
        Page title and extracted text.
    """
    engine = await _get_engine()
    return await engine.scrape(url, selector or None, timeout_ms=timeout_ms)


async def _shutdown_engine() -> None:
    """Close resources owned by the MCP process."""
    global _engine
    if _engine is not None:
        await _engine.stop()
        _engine = None


def main():
    try:
        mcp.run(transport="stdio")
    finally:
        asyncio.run(_shutdown_engine())


if __name__ == "__main__":
    main()
