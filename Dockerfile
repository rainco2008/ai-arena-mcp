FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BROWSER_CHANNEL=chromium \
    HEADLESS=1 \
    GEMINI_SEARCH_BROWSER_BACKEND=playwright \
    GEMINI_SEARCH_CHROME_EXTRA_ARGS="--no-sandbox --disable-dev-shm-usage --enable-gpu --use-gl=angle --enable-webgl --disable-blink-features=AutomationControlled"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY gemini_search/ gemini_search/
COPY gemini_search_mcp/ gemini_search_mcp/
COPY mcp_server.py .
COPY docker/entrypoint.sh /usr/local/bin/gemini-search-entrypoint.sh

RUN pip install --no-cache-dir -e ".[cloakbrowser]" \
    && python -m playwright install chromium --with-deps \
    && chmod +x /usr/local/bin/gemini-search-entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["gemini-search-entrypoint.sh"]
CMD ["python", "-m", "gemini_search", "--host", "0.0.0.0", "--port", "8080", "--browser-backend", "playwright", "--channel", "chromium"]
