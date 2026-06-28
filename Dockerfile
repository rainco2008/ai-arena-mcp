FROM mcr.microsoft.com/playwright/python:v1.52.0-noble

WORKDIR /app
COPY pyproject.toml .
COPY google_ai_mode/ google_ai_mode/

RUN pip install --no-cache-dir -e . && \
    playwright install chromium

EXPOSE 8080

CMD ["python", "-m", "google_ai_mode", "--channel", "chromium", "--port", "8080"]
