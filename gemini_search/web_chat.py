"""Browser automation adapters for personal web-chat research."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional


def normalize_web_chat_provider(provider: Optional[str]) -> str:
    value = (provider or "disabled").strip().lower()
    aliases = {
        "": "disabled",
        "none": "disabled",
        "off": "disabled",
        "disabled": "disabled",
        "deepseek": "deepseek",
        "deepseek_web": "deepseek",
        "chatgpt": "chatgpt",
        "chatgpt_web": "chatgpt",
        "openai": "chatgpt",
        "gemini": "gemini",
        "gemini_web": "gemini",
    }
    if value not in aliases:
        raise ValueError("web_chat_provider must be one of: disabled, deepseek, chatgpt, gemini")
    return aliases[value]


async def _maybe_await(value):
    if hasattr(value, "__await__"):
        return await value
    return value


async def _first_visible(page, selectors: list[str], timeout_ms: int = 1500):
    for selector in selectors:
        locator = page.locator(selector).last
        try:
            await locator.wait_for(state="visible", timeout=timeout_ms)
            return locator
        except Exception:
            continue
    return None


async def _visible_count(page, selector: str) -> int:
    try:
        return await page.locator(selector).count()
    except Exception:
        return 0


class WebChatProvider:
    """Ask hosted model websites through a persistent local browser profile."""

    def __init__(self):
        self._config: dict = {}
        self._lock = asyncio.Lock()
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    @property
    def provider(self) -> str:
        return normalize_web_chat_provider(self._config.get("web_chat_provider"))

    async def start(self, **config):
        self._config = dict(config)

    async def stop(self):
        for resource in (self._context, self._browser):
            if resource is not None and hasattr(resource, "close"):
                try:
                    await _maybe_await(resource.close())
                except Exception:
                    pass
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                pass
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    async def ask(self, prompt: str, timeout_ms: int = 120000) -> str:
        provider = self.provider
        if provider == "disabled":
            raise RuntimeError("WEB_CHAT_PROVIDER is disabled")
        async with self._lock:
            page = await self._page_for_provider(provider)
            if provider == "deepseek":
                return await self._ask_generic(
                    page,
                    prompt,
                    url="https://chat.deepseek.com/",
                    input_selectors=[
                        "textarea",
                        "div[contenteditable='true']",
                        "[role='textbox']",
                    ],
                    answer_selectors=[
                        ".ds-markdown",
                        ".markdown",
                        "[class*='markdown']",
                        "[data-message-author-role='assistant']",
                    ],
                    timeout_ms=timeout_ms,
                )
            if provider == "chatgpt":
                return await self._ask_generic(
                    page,
                    prompt,
                    url="https://chatgpt.com/",
                    input_selectors=[
                        "#prompt-textarea",
                        "textarea",
                        "div[contenteditable='true']",
                        "[role='textbox']",
                    ],
                    answer_selectors=[
                        "[data-message-author-role='assistant']",
                        ".markdown",
                        "[class*='markdown']",
                    ],
                    timeout_ms=timeout_ms,
                )
            if provider == "gemini":
                return await self._ask_generic(
                    page,
                    prompt,
                    url="https://gemini.google.com/app",
                    input_selectors=[
                        "rich-textarea div[contenteditable='true']",
                        "div[contenteditable='true']",
                        "textarea",
                        "[role='textbox']",
                    ],
                    answer_selectors=[
                        "message-content",
                        ".model-response-text",
                        "[class*='model-response']",
                        "[class*='markdown']",
                    ],
                    timeout_ms=timeout_ms,
                )
            raise RuntimeError(f"Unsupported web chat provider: {provider}")

    async def _page_for_provider(self, provider: str):
        if self._page is not None:
            return self._page

        backend = (self._config.get("web_chat_backend") or "playwright").strip().lower()
        if backend == "cloakbrowser":
            self._page = await self._launch_cloakbrowser()
            return self._page
        self._page = await self._launch_playwright(provider)
        return self._page

    async def _launch_playwright(self, provider: str):
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                'Web chat automation requires Scrapling browser dependencies. Install with: pip install "scrapling[all]"'
            ) from exc

        profile_dir = self._profile_dir(provider)
        profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        launch_options = {
            "headless": bool(self._config.get("web_chat_headless", False)),
        }
        proxy = self._config.get("proxy_server")
        if proxy:
            launch_options["proxy"] = {"server": proxy}
        self._context = await self._playwright.chromium.launch_persistent_context(
            str(profile_dir),
            **launch_options,
        )
        pages = self._context.pages
        return pages[0] if pages else await self._context.new_page()

    async def _launch_cloakbrowser(self):
        try:
            import cloakbrowser
        except ImportError as exc:
            raise RuntimeError('CloakBrowser backend requires: pip install -e ".[cloakbrowser]"') from exc
        kwargs = {
            "headless": bool(self._config.get("web_chat_headless", False)),
        }
        proxy = self._config.get("proxy_server")
        if proxy:
            kwargs["proxy"] = proxy
        profile_dir = self._profile_dir(self.provider)
        profile_dir.mkdir(parents=True, exist_ok=True)
        if hasattr(cloakbrowser, "launch_persistent_context_async"):
            self._context = await cloakbrowser.launch_persistent_context_async(str(profile_dir), **kwargs)
            return await _maybe_await(self._context.new_page())
        launcher = getattr(cloakbrowser, "launch_async", None) or getattr(cloakbrowser, "launch", None)
        if launcher is None:
            raise RuntimeError("cloakbrowser package does not expose launch_async or launch")
        self._browser = await _maybe_await(launcher(**kwargs))
        if hasattr(self._browser, "new_context"):
            self._context = await _maybe_await(self._browser.new_context())
            return await _maybe_await(self._context.new_page())
        return await _maybe_await(self._browser.new_page())

    def _profile_dir(self, provider: str) -> Path:
        configured = self._config.get("web_chat_profile_dir") or os.environ.get("WEB_CHAT_PROFILE_DIR")
        if configured:
            return Path(configured).expanduser().resolve()
        return (Path.cwd() / "profiles" / "web-chat" / provider).resolve()

    async def _ask_generic(
        self,
        page,
        prompt: str,
        url: str,
        input_selectors: list[str],
        answer_selectors: list[str],
        timeout_ms: int,
    ) -> str:
        if not (page.url or "").startswith(url):
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

        input_box = await _first_visible(page, input_selectors, timeout_ms=5000)
        if input_box is None:
            title = ""
            try:
                title = await page.title()
            except Exception:
                pass
            raise RuntimeError(
                "Could not find a visible chat input. Open the site in headed mode, log in, "
                f"then retry. Current title: {title or '(unknown)'}"
            )

        baseline = await self._answer_count(page, answer_selectors)
        await input_box.click()
        await self._fill_input(input_box, prompt)
        await page.keyboard.press("Enter")
        return await self._wait_for_new_answer(page, answer_selectors, baseline, timeout_ms)

    async def _fill_input(self, input_box, prompt: str) -> None:
        try:
            await input_box.fill(prompt)
            return
        except Exception:
            pass
        await input_box.click()
        await input_box.evaluate(
            """(el, text) => {
                el.focus();
                if ('value' in el) {
                    el.value = text;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                } else {
                    el.textContent = text;
                    el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
                }
            }""",
            prompt,
        )

    async def _answer_count(self, page, selectors: list[str]) -> int:
        total = 0
        for selector in selectors:
            total = max(total, await _visible_count(page, selector))
        return total

    async def _wait_for_new_answer(
        self,
        page,
        selectors: list[str],
        baseline: int,
        timeout_ms: int,
    ) -> str:
        deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
        last_text = ""
        stable_since = None
        while asyncio.get_running_loop().time() < deadline:
            text = await self._latest_answer_text(page, selectors, baseline)
            if text:
                if text != last_text:
                    last_text = text
                    stable_since = asyncio.get_running_loop().time()
                elif stable_since and asyncio.get_running_loop().time() - stable_since >= 3:
                    return text
            await asyncio.sleep(1)
        if last_text:
            return last_text
        raise RuntimeError("Timed out waiting for a model answer")

    async def _latest_answer_text(self, page, selectors: list[str], baseline: int) -> str:
        for selector in selectors:
            locator = page.locator(selector)
            try:
                count = await locator.count()
            except Exception:
                continue
            if count <= 0 or count < baseline:
                continue
            try:
                text = await locator.nth(count - 1).inner_text(timeout=1000)
            except Exception:
                continue
            text = " ".join((text or "").split()).strip()
            if text:
                return text
        return ""
