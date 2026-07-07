FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HEADLESS=1 \
    GEMINI_SEARCH_PROVIDER=scrapling \
    GEMINI_SEARCH_SCRAPE_BACKEND=scrapling

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY gemini_search/ gemini_search/
COPY gemini_search_mcp/ gemini_search_mcp/
COPY content_factory/ content_factory/
COPY content_factory_cli.py .
COPY scripts/ scripts/
COPY sql/ sql/
COPY mcp_server.py .
COPY docker/entrypoint.sh /usr/local/bin/contentpilot-entrypoint.sh

RUN pip install --no-cache-dir -e ".[all]" \
    && scrapling install \
    && chmod +x /usr/local/bin/contentpilot-entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["contentpilot-entrypoint.sh"]
CMD ["python", "-m", "gemini_search", "--host", "0.0.0.0", "--port", "8080", "--scrape-backend", "scrapling"]
