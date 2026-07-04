"""Windows desktop launcher for the local web console."""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from gemini_search.server import _initial_config, app


if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent


def _find_port(start: int = 8080, attempts: int = 50) -> int:
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No available local port from {start} to {start + attempts - 1}")


def _open_browser(port: int) -> None:
    time.sleep(2)
    webbrowser.open(f"http://127.0.0.1:{port}/")


def _prepare_environment() -> None:
    (BASE_DIR / "profiles" / "default").mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "logs").mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("GEMINI_SEARCH_PROVIDER", "scrapling")
    os.environ.setdefault("GEMINI_SEARCH_SCRAPE_BACKEND", "scrapling")
    os.environ.setdefault("WEB_CHAT_PROVIDER", "disabled")
    os.environ.setdefault("WEB_CHAT_BACKEND", "playwright")
    os.environ.setdefault("WEB_CHAT_PROFILE_DIR", str(BASE_DIR / "profiles" / "web-chat"))
    os.environ.setdefault("HEADLESS", "0")
    os.environ.setdefault("WEB_CHAT_HEADLESS", "0")


def main() -> None:
    _prepare_environment()
    port = _find_port(int(os.environ.get("GEMINI_SEARCH_PORT", "8080")))
    app.state.config = _initial_config()

    threading.Thread(target=_open_browser, args=(port,), daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
