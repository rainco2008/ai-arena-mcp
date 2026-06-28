"""Core engine: drive Google AI Mode via Playwright headless Chrome.

Cross-platform (Windows/Linux/macOS). Self-contained — launches its own
Chrome instance with stealth patches, no external browser required.
"""
import asyncio
import sys
import os
from playwright.async_api import async_playwright, Page, Browser, BrowserContext


def _channel_fallback(preferred: str) -> list[str]:
    """Return ordered list of browser channels to try."""
    order = ["chrome", "msedge", "chromium"]
    if preferred in order:
        order.remove(preferred)
        order.insert(0, preferred)
    return order


STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
window.chrome = {runtime: {}, loadTimes: () => {}, csi: () => {}};
const _origQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (p) => (
  p.name === 'notifications'
    ? Promise.resolve({state: Notification.permission})
    : _origQuery(p)
);
Object.defineProperty(navigator, 'plugins', {
  get: () => Object.assign([
    {name:'Chrome PDF Plugin',filename:'internal-pdf-viewer'},
    {name:'Chrome PDF Viewer',filename:'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
    {name:'Native Client',filename:'internal-nacl-plugin'}
  ], {length: 3})
});
Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 0});
Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
"""


class AIModeSession:
    """A single AI Mode browser tab that can handle requests."""

    def __init__(self, page: Page):
        self.page = page
        self.busy = False
        self.request_count = 0

    async def ask(self, question: str, timeout_ms: int = 60000) -> str:
        textarea = self.page.locator("textarea").last
        await textarea.wait_for(state="visible", timeout=10000)
        await textarea.fill(question)
        await textarea.press("Enter")

        await self._wait_for_new_turn()

        prev_text = ""
        stable = 0
        for _ in range(timeout_ms // 400):
            text = await self._extract_response()
            if text and text == prev_text:
                stable += 1
                # Short answers stabilize faster
                needed = 4 if len(text) < 50 else 7
                if stable >= needed:
                    break
            else:
                stable = 0
                prev_text = text
            await self.page.wait_for_timeout(400)

        self.request_count += 1
        return prev_text

    async def ask_stream(self, question: str, timeout_ms: int = 60000):
        textarea = self.page.locator("textarea").last
        await textarea.wait_for(state="visible", timeout=10000)
        await textarea.fill(question)
        await textarea.press("Enter")

        await self._wait_for_new_turn()

        prev_text = ""
        stable = 0
        for _ in range(timeout_ms // 250):
            text = await self._extract_response()
            if text and len(text) > len(prev_text):
                delta = text[len(prev_text):]
                yield delta
                prev_text = text
                stable = 0
            elif text == prev_text and text:
                stable += 1
                needed = 6 if len(text) < 50 else 12
                if stable >= needed:
                    break
            await self.page.wait_for_timeout(250)

        self.request_count += 1

    async def _wait_for_new_turn(self):
        """Wait for Google to start rendering a new response turn."""
        initial_count = await self.page.evaluate("""() =>
            document.querySelectorAll('[dir="ltr"].mZJni, [data-subtree="aimc"]').length
        """)
        for _ in range(40):
            count = await self.page.evaluate("""() =>
                document.querySelectorAll('[dir="ltr"].mZJni, [data-subtree="aimc"]').length
            """)
            if count > initial_count:
                break
            # Also check if existing last block has new short content
            text = await self._extract_response()
            if text and len(text) < 20 and text != await self._extract_response():
                break
            await self.page.wait_for_timeout(250)
        await self.page.wait_for_timeout(200)

    async def _extract_response(self) -> str:
        return await self.page.evaluate("""() => {
            const blocks = document.querySelectorAll('[dir="ltr"].mZJni');
            if (blocks.length > 0) return blocks[blocks.length - 1].innerText || '';
            const turns = document.querySelectorAll('[data-subtree="aimc"]');
            if (turns.length > 0) return turns[turns.length - 1].innerText || '';
            return '';
        }""")

    async def is_healthy(self) -> bool:
        try:
            url = self.page.url
            return "google" in url and not self.page.is_closed()
        except Exception:
            return False


class SessionPool:
    """Pool of AI Mode browser sessions for concurrent requests."""

    def __init__(self, size: int = 1):
        self.size = size
        self.sessions: list[AIModeSession] = []
        self.pw = None
        self.browser = None
        self.context = None
        self._lock = asyncio.Lock()
        self._cdp_url: str | None = None
        self._channel: str = "chrome"

    async def start(self, cdp_url: str = None, headless: bool = True, channel: str = "chrome"):
        """Initialize the pool with browser sessions."""
        self._cdp_url = cdp_url
        self._channel = channel
        self.pw = await async_playwright().start()

        if cdp_url:
            self.browser = await self.pw.chromium.connect_over_cdp(cdp_url)
            self.context = self.browser.contexts[0] if self.browser.contexts else await self.browser.new_context()
        else:
            # Try channels in order: requested → chrome → msedge → chromium
            launch_error = None
            for ch in _channel_fallback(channel):
                try:
                    self.browser = await self.pw.chromium.launch(
                        headless=headless,
                        channel=ch if ch != "chromium" else None,
                        args=[
                            "--no-sandbox",
                            "--disable-blink-features=AutomationControlled",
                            "--disable-dev-shm-usage",
                            "--disable-infobars",
                            "--disable-background-timer-throttling",
                            "--disable-renderer-backgrounding",
                        ],
                    )
                    self._channel = ch
                    break
                except Exception as e:
                    launch_error = e
                    continue
            else:
                raise RuntimeError(
                    f"No browser found. Install Chrome or run: playwright install chrome\n"
                    f"Last error: {launch_error}"
                )

            self.context = await self.browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720},
                locale="en-US",
            )
            await self.context.add_init_script(STEALTH_SCRIPT)

        for i in range(self.size):
            session = await self._create_session()
            self.sessions.append(session)
            if i < self.size - 1:
                await asyncio.sleep(2)

    async def _create_session(self) -> AIModeSession:
        """Create a new AI Mode session (page navigated to AI Mode)."""
        page = await self.context.new_page()
        await page.goto(
            "https://www.google.com/search?q=hello&hl=en&gl=us",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        await page.wait_for_timeout(2000)

        if "/sorry/" in page.url:
            raise RuntimeError(
                f"CAPTCHA detected: {page.url}\n"
                "Solutions:\n"
                "  1. Use --cdp-url to connect to a real Chrome\n"
                "  2. Use --channel=chrome to use system Chrome instead of Chromium\n"
                "  3. Set up a proxy with --proxy"
            )

        ai_link = page.locator("a:has-text('AI Mode')")
        if await ai_link.count() > 0:
            await ai_link.first.click()
            await page.wait_for_timeout(4000)
        else:
            raise RuntimeError("AI Mode tab not found — Google may have changed their UI")

        if "udm=50" not in page.url:
            raise RuntimeError(f"Failed to enter AI Mode. URL: {page.url}")

        return AIModeSession(page)

    async def acquire(self) -> AIModeSession:
        """Get a free session, waiting if all are busy."""
        while True:
            async with self._lock:
                for s in self.sessions:
                    if not s.busy:
                        s.busy = True
                        if not await s.is_healthy():
                            await self._recover_session(s)
                        return s
            await asyncio.sleep(0.1)

    def release(self, session: AIModeSession):
        session.busy = False

    async def _recover_session(self, session: AIModeSession):
        """Recreate a broken session."""
        try:
            await session.page.close()
        except Exception:
            pass
        idx = self.sessions.index(session)
        new_session = await self._create_session()
        new_session.busy = True
        self.sessions[idx] = new_session
        session.page = new_session.page
        session.request_count = 0

    async def stop(self):
        for s in self.sessions:
            try:
                await s.page.close()
            except Exception:
                pass
        if self.browser and not self._cdp_url:
            await self.browser.close()
        if self.pw:
            await self.pw.stop()


async def e2e_test():
    """End-to-end verification."""
    cdp_url = os.environ.get("CDP_URL")
    channel = os.environ.get("CHROME_CHANNEL", "chrome")
    headless = os.environ.get("HEADLESS", "1") == "1"

    pool = SessionPool(size=1)
    print(f"Starting... (cdp={cdp_url or 'self-launch'}, channel={channel}, headless={headless})")
    await pool.start(cdp_url=cdp_url, headless=headless, channel=channel)

    session = await pool.acquire()
    try:
        print(f"AI Mode: {session.page.url[:80]}")

        print("\n[1] ask: 'what is 2+2?'")
        answer = await session.ask("what is 2+2? answer only the number")
        print(f"    → {repr(answer)}")

        print("\n[2] stream: 'explain python in 2 sentences'")
        full = ""
        async for chunk in session.ask_stream("explain python in 2 sentences"):
            full += chunk
            print(f"    +{len(chunk):4d} chars")
        print(f"    Total: {len(full)} chars")
        print(f"    Preview: {full[:150]}")

        ok = "2" in answer or "4" in answer
        print(f"\n{'PASS' if ok and len(full) > 20 else 'FAIL'}")
    finally:
        pool.release(session)
        await pool.stop()


if __name__ == "__main__":
    asyncio.run(e2e_test())
