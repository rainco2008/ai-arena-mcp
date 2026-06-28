"""Pure-protocol Google AI Mode client — no browser, no JS engine.

Flow:
1. GET https://www.google.com/search?q=<q>&udm=50 with cookies → 360KB HTML
2. Extract tokens (srtst, xsrf_folif, xsrf_folwr, garc, lro_token, ei) from data-* attributes
3. GET /async/folwr?<tokens>&q=<question> → streaming HTML response with AI answer
4. Parse text from HTML chunks

Rate-limit handling: Google serves HTTP 429 + CAPTCHA when it detects burst
patterns from one IP/cookie. CookiePool rotates multiple cookie sets, marks
unhealthy ones for cooldown, and throttles request spacing.
"""
import re
import ssl
import time
import random
import threading
import urllib.request
import urllib.parse
import urllib.error
from html.parser import HTMLParser

try:
    from curl_cffi import requests as _cf_requests
    _HAS_CFFI = True
except ImportError:
    _HAS_CFFI = False


_SEARCH_URL = "https://www.google.com.hk/search?q={q}&hl=en&gl=us&udm=50&aep=1&ntc=1"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"

_TOKEN_ATTRS = [
    "data-srtst",
    "data-xsrf-folif-token",
    "data-xsrf-folwr-token",
    "data-garc",
    "data-lro-token",
    "data-lro-signature",
    "data-ei",
    "data-stkp",
]


def extract_sca_esv(html):
    """Extract sca_esv hash from page."""
    m = re.search(r'sca_esv=([a-f0-9]+)', html) or re.search(r'"sca_esv":"([a-f0-9]+)"', html)
    return m.group(1) if m else ""


def extract_ved(html):
    """Extract ved from the AI Mode tab.

    The active AI Mode tab is <a aria-current="page" ... data-ved="...">.
    vet is derived as: vet = "1" + ved + "..i"
    """
    # Primary: AI Mode tab has aria-current="page" and data-ved
    m = re.search(r'aria-current="page"[^>]*data-ved="([^"]+)"', html)
    if m:
        return m.group(1)
    m = re.search(r'data-ved="([^"]+)"[^>]*aria-current="page"', html)
    if m:
        return m.group(1)
    # Fallback: data-ved nearest before "AI Mode" text
    idx = html.find(">AI Mode<")
    if idx < 0:
        idx = html.find("AI Mode")
    if idx > -1:
        chunk = html[max(0, idx - 500):idx]
        matches = re.findall(r'data-ved="([^"]+)"', chunk)
        if matches:
            return matches[-1]
    return ""


def _ssl_ctx():
    return ssl.create_default_context()


def _update_cookies(existing, set_cookie_headers):
    """Merge Set-Cookie headers into existing cookie string."""
    if not set_cookie_headers:
        return existing
    cookie_map = {}
    for pair in existing.split("; "):
        if "=" in pair:
            k, v = pair.split("=", 1)
            cookie_map[k.strip()] = v
    for header in set_cookie_headers:
        pair = header.split(";")[0]
        if "=" in pair:
            k, v = pair.split("=", 1)
            cookie_map[k.strip()] = v.strip()
    return "; ".join(f"{k}={v}" for k, v in cookie_map.items())


def _fetch(url, cookies, referer=None, max_redirects=5, cookie_sink=None, proxy=None):
    """Fetch a URL with cookies, following redirects manually.

    Prefers curl_cffi (Chrome TLS/HTTP2 fingerprint) when available — it
    triggers Google's anti-bot far less than urllib. Falls back to urllib.
    """
    headers = {
        "User-Agent": _UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        'Sec-CH-UA': '"Chromium";v="148", "Not?A_Brand";v="24", "Google Chrome";v="148"',
        "Sec-CH-UA-Mobile": "?0",
        'Sec-CH-UA-Platform': '"Windows"',
        "Upgrade-Insecure-Requests": "1",
        "Cookie": cookies,
    }
    if referer:
        headers["Referer"] = referer

    if _HAS_CFFI:
        return _fetch_cffi(url, headers, cookie_sink, cookies, proxy)
    return _fetch_urllib(url, headers, cookie_sink, cookies, proxy, max_redirects)


def _fetch_cffi(url, headers, cookie_sink, cookies, proxy):
    """curl_cffi path — impersonates Chrome TLS/HTTP2 fingerprint."""
    proxies = {"http": proxy, "https": proxy} if proxy else None
    resp = _cf_requests.get(
        url, headers=headers, proxies=proxies,
        impersonate="chrome", timeout=30, allow_redirects=True,
    )
    if resp.status_code == 429:
        raise urllib.error.HTTPError(url, 429, "Too Many Requests", resp.headers, None)
    body = resp.text
    set_cookies = resp.headers.get_list("set-cookie") if hasattr(resp.headers, "get_list") else []
    if set_cookies and cookie_sink is not None:
        cookie_sink["cookies"] = _update_cookies(cookie_sink.get("cookies", cookies), set_cookies)
    return body, resp


def _fetch_urllib(url, headers, cookie_sink, cookies, proxy, max_redirects):
    """urllib fallback path."""
    ctx = _ssl_ctx()
    if proxy:
        proxy_handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        https_handler = urllib.request.HTTPSHandler(context=ctx)
        opener = urllib.request.build_opener(proxy_handler, https_handler)
    else:
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))

    body = ""
    resp = None
    for _ in range(max_redirects):
        req = urllib.request.Request(url, headers=headers, method="GET")
        resp = opener.open(req, timeout=30)
        set_cookies = resp.headers.get_all("Set-Cookie") or []
        if set_cookies and cookie_sink is not None:
            cookie_sink["cookies"] = _update_cookies(cookie_sink.get("cookies", cookies), set_cookies)
            headers["Cookie"] = cookie_sink["cookies"]
        body = resp.read().decode("utf-8", errors="replace")
        if resp.status in (301, 302, 303, 307, 308):
            loc = resp.headers.get("Location")
            if not loc:
                break
            url = urllib.parse.urljoin(url, loc)
            continue
        return body, resp
    return body, resp


def get_cookies(seed_url="https://www.google.com/"):
    """Bootstrap cookies by visiting Google homepage (returns cookie string)."""
    req = urllib.request.Request(seed_url, headers={"User-Agent": _UA})
    ctx = _ssl_ctx()
    resp = urllib.request.urlopen(req, context=ctx, timeout=15)
    cookies = []
    for header in resp.headers.get_all("Set-Cookie") or []:
        pair = header.split(";")[0]
        if "=" in pair:
            cookies.append(pair.strip())
    return "; ".join(cookies)


def extract_tokens(html):
    """Extract AI Mode tokens from the search page HTML.

    Tokens live on two elements:
    - A div with data-srtst/data-garc/data-lro-*/data-xsrf-*/data-ei
    - A separate div with data-stkp
    """
    # Detect CAPTCHA / rate-limit / soft-block pages (they have no tokens)
    if "/sorry/" in html or "id='captcha'" in html or 'id="captcha"' in html:
        raise urllib.error.HTTPError("captured", 429, "CAPTCHA/rate-limit page", {}, None)
    if len(html) < 5000 and "Enable JavaScript" in html:
        raise urllib.error.HTTPError("captured", 429, "JS-required shell (soft block)", {}, None)

    tokens = {}

    # Main token element
    token_el_match = re.search(
        r'<div([^>]*data-srtst="[^"]*"[^>]*)>', html
    )
    if not token_el_match:
        raise urllib.error.HTTPError("captured", 429, "No token element (likely rate-limited)", {}, None)

    attrs_str = token_el_match.group(1)
    for attr in _TOKEN_ATTRS:
        m = re.search(re.escape(attr) + r'="([^"]+)"', attrs_str)
        if m:
            tokens[attr] = m.group(1)

    # data-stkp is on a separate div
    stkp_match = re.search(r'data-stkp="([^"]+)"', html)
    if stkp_match:
        tokens["data-stkp"] = stkp_match.group(1)

    if "data-srtst" not in tokens:
        raise urllib.error.HTTPError("captured", 429, "data-srtst missing (likely rate-limited)", {}, None)

    return tokens


def build_folwr_url(tokens, question, sca_esv="", ved="", base="https://www.google.com.hk"):
    """Build the /async/folwr streaming request URL."""
    srtst = tokens["data-srtst"]
    xsrf = tokens["data-xsrf-folwr-token"]
    garc = tokens["data-garc"]
    lro = tokens.get("data-lro-token", "")
    mlros = tokens.get("data-lro-signature", "")
    stkp = tokens.get("data-stkp", "")
    ei = tokens["data-ei"]
    vet = f"1{ved}..i" if ved else ""

    params = {
        "srtst": srtst,
        "garc": garc,
        "mlro": lro,
        "mlros": mlros,
        "ei": ei,
        "q": question,
        "yv": "3",
        "vet": vet,
        "ved": ved,
        "aep": "1",
        "gl": "us",
        "hl": "en",
        "sca_esv": sca_esv,
        "udm": "50",
        "stkp": stkp,
        "cs": "0",
        "async": f"_fmt:adl,_xsrf:{xsrf}",
    }
    params = {k: v for k, v in params.items() if v}
    query = urllib.parse.urlencode(params)
    return f"{base}/async/folwr?{query}"


class _TextExtractor(HTMLParser):
    """Extract AI answer text from folwr HTML.

    The answer body lives in <div class="n6owBd ..."> (answer component)
    containing <div class="pTRUV" dir="ltr"> (formatted answer text).
    Search citations and UI controls use different containers.
    """

    def __init__(self):
        super().__init__()
        self.text_parts = []
        self._div_stack = []
        self._skip_stack = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "button"):
            self._skip_stack.append(tag)
            return
        if tag == "div":
            self._div_stack.append(dict(attrs).get("class", ""))

    def handle_endtag(self, tag):
        if tag in ("script", "style", "button"):
            if self._skip_stack:
                self._skip_stack.pop()
            return
        if tag == "div" and self._div_stack:
            self._div_stack.pop()

    def _in_answer(self):
        # n6owBd = answer component wrapper, pTRUV = formatted answer text
        return any("n6owBd" in c or "pTRUV" in c for c in self._div_stack)

    def handle_data(self, data):
        if self._skip_stack:
            return
        if self._in_answer():
            stripped = data.strip()
            if stripped:
                self.text_parts.append(stripped)

    def get_text(self):
        return " ".join(self.text_parts)


# UI noise phrases to strip from tail of extracted text
_UI_NOISE = [
    "Copy", "Share", "Good response", "Bad response", "About this result",
    "View related links", "public link", "AI responses may include mistakes",
    "Tell me which", "Would you like", "This public link is valid",
    "If you share with", "cannot be deleted",
]


def parse_response_text(html_chunk):
    """Parse accumulated HTML response to extract AI answer text."""
    extractor = _TextExtractor()
    try:
        extractor.feed(html_chunk)
    except Exception:
        pass
    text = extractor.get_text()
    # Trim trailing UI noise
    changed = True
    while changed:
        changed = False
        for noise in _UI_NOISE:
            if text.endswith(noise) or text.endswith(noise + "."):
                text = text[: -len(noise)].rstrip(" .,")
                changed = True
    return text


class CookiePool:
    """Rotate multiple cookie sets to distribute rate-limit pressure.

    Each entry tracks health: on HTTP 429 the cookie enters a cooldown
    period during which it is skipped. A global minimum interval between
    requests (plus jitter) makes traffic look less bursty.
    """

    def __init__(self, cookies_list=None, min_interval=6, cooldown=180):
        self._lock = threading.Lock()
        self.min_interval = min_interval
        self.cooldown = cooldown
        now = time.time()
        self._entries = []
        for c in (cookies_list or []):
            self._entries.append({
                "cookies": c,
                "available_at": now,
                "uses": 0,
                "fails": 0,
            })
        self._last_request = 0.0

    def acquire(self):
        """Block until a healthy cookie is available, return (index, cookies)."""
        while True:
            with self._lock:
                now = time.time()
                # Global spacing between requests regardless of cookie
                wait_global = self._last_request + self.min_interval - now
                candidates = [e for e in self._entries if e["available_at"] <= now]
                if candidates and wait_global <= 0:
                    # Pick least-recently-failed, then least-used
                    candidates.sort(key=lambda e: (e["fails"], e["uses"]))
                    entry = candidates[0]
                    entry["uses"] += 1
                    self._last_request = now
                    idx = self._entries.index(entry)
                    return idx, entry["cookies"]
                wait = max(wait_global, 0.5)
                if not candidates:
                    # All cooling down — wait for the earliest available
                    next_avail = min(e["available_at"] for e in self._entries)
                    wait = max(next_avail - now, 0.5)
            time.sleep(wait + random.uniform(0, 1.0))

    def mark_ok(self, idx, updated_cookies=None):
        with self._lock:
            e = self._entries[idx]
            if updated_cookies:
                e["cookies"] = updated_cookies

    def mark_429(self, idx):
        with self._lock:
            e = self._entries[idx]
            e["fails"] += 1
            e["available_at"] = time.time() + self.cooldown
            # Exponential cooldown on repeated fails
            e["available_at"] += min(e["fails"] - 1, 5) * 60

    def stats(self):
        with self._lock:
            now = time.time()
            return [
                {
                    "index": i,
                    "uses": e["uses"],
                    "fails": e["fails"],
                    "cooldown_remaining": max(0, int(e["available_at"] - now)),
                }
                for i, e in enumerate(self._entries)
            ]


class AIModeClient:
    """Pure-protocol AI Mode client.

    Single-cookie usage: pass `cookies=...`.
    Multi-cookie rotation: pass `cookie_pool=CookiePool([...])`.
    """

    def __init__(self, cookies=None, proxy=None, cookie_pool=None):
        self.cookies = cookies or ""
        self.proxy = proxy
        self.cookie_pool = cookie_pool
        self._pool_idx = None
        self.tokens = None
        self.sca_esv = ""
        self.ved = ""
        self.session_query = ""
        self.page_html = None

    def _get_cookies(self):
        if self.cookie_pool:
            idx, cookies = self.cookie_pool.acquire()
            self._pool_idx = idx
            self.cookies = cookies
            return cookies
        if not self.cookies:
            self.cookies = get_cookies()
        return self.cookies

    def _report(self, ok, updated_cookies=None):
        if self.cookie_pool and self._pool_idx is not None:
            if ok:
                self.cookie_pool.mark_ok(self._pool_idx, updated_cookies)
            else:
                self.cookie_pool.mark_429(self._pool_idx)

    def init_session(self, query="hello"):
        """Load the AI Mode page for a query, extract tokens.

        The query binds the session — folwr must use the SAME query.
        """
        self._get_cookies()

        url = _SEARCH_URL.format(q=urllib.parse.quote(query))
        sink = {"cookies": self.cookies}
        try:
            html, _ = _fetch(url, self.cookies, cookie_sink=sink, proxy=self.proxy)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                self._report(False)
            raise
        self.cookies = sink["cookies"]
        self._report(True, sink["cookies"])
        self.page_html = html
        self.tokens = extract_tokens(html)
        self.sca_esv = extract_sca_esv(html)
        self.ved = extract_ved(html)
        self.session_query = query
        return self.tokens

    def ask(self, question, timeout=60, retries=3):
        """Ask a question, return full response text.

        Each question starts a fresh session (new page load + folwr).
        Retries on rate-limit (429): with a cookie pool, the next attempt
        picks a different cookie; otherwise exponential backoff.
        """
        last_err = None
        for attempt in range(retries):
            try:
                self.init_session(question)
                url = build_folwr_url(self.tokens, question, self.sca_esv, self.ved)
                sink = {"cookies": self.cookies}
                body, _ = _fetch(url, self.cookies, referer="https://www.google.com.hk/", cookie_sink=sink, proxy=self.proxy)
                self.cookies = sink["cookies"]
                self._report(True, sink["cookies"])
                text = parse_response_text(body)
                if text:
                    return text
                if attempt < retries - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                return text
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code == 429:
                    # pool already marked this cookie via init_session or here
                    self._report(False)
                    if self.cookie_pool:
                        continue  # next attempt uses a different cookie
                    time.sleep(5 * (attempt + 1))
                    continue
                raise
        if last_err:
            raise last_err
        return ""

    def ask_stream(self, question, timeout=60):
        """Ask a question, yield text chunks as they stream."""
        self.init_session(question)
        url = build_folwr_url(self.tokens, question, self.sca_esv, self.ved)
    def ask_stream(self, question, timeout=60, retries=3):
        """Ask a question, yield text chunks as they stream.

        Retries on rate-limit (429) with exponential backoff.
        """
        last_err = None
        for attempt in range(retries):
            try:
                self.init_session(question)
                url = build_folwr_url(self.tokens, question, self.sca_esv, self.ved)
                headers = {
                    "User-Agent": _UA,
                    "Accept": "text/html,*/*",
                    "Cookie": self.cookies,
                    "Referer": "https://www.google.com.hk/",
                }
                ctx = _ssl_ctx()
                req = urllib.request.Request(url, headers=headers, method="GET")

                accumulated = ""
                prev_text = ""
                resp = urllib.request.urlopen(req, context=ctx, timeout=timeout)
                has_yielded = False
                for raw in resp:
                    chunk = raw.decode("utf-8", errors="replace")
                    accumulated += chunk
                    text = parse_response_text(accumulated)
                    if len(text) > len(prev_text):
                        yield text[len(prev_text):]
                        prev_text = text
                        has_yielded = True
                if has_yielded or prev_text:
                    return
                # Empty result, retry
                if attempt < retries - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                return
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code == 429:
                    time.sleep(5 * (attempt + 1))
                    continue
                raise
        if last_err:
            raise last_err


if __name__ == "__main__":
    import sys

    cookies = open("/tmp/all_cookies.txt").read().strip()
    client = AIModeClient(cookies=cookies)

    print("Initializing session...")
    tokens = client.init_session("hello")
    print(f"Tokens: {list(tokens.keys())}")
    print(f"  srtst: {tokens.get('data-srtst','')[:50]}...")
    print(f"  ei: {tokens.get('data-ei','')}")

    print("\n[1] ask: 'what is 2+2?'")
    answer = client.ask("what is 2+2? answer only the number")
    print(f"  → {answer[:200]}")

    print("\n[2] stream: 'explain python in 2 sentences'")
    full = ""
    for chunk in client.ask_stream("explain python in 2 sentences"):
        full += chunk
        print(f"  +{len(chunk)} chars")
    print(f"  Total: {len(full)} chars: {full[:200]}")
