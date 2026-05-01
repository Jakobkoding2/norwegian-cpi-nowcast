FROM python:3.11-slim

WORKDIR /app

COPY ../pyproject.toml .
RUN pip install --no-cache-dir ".[" && pip install --no-cache-dir hatchling && pip install --no-cache-dir .

COPY . /app/scraper
COPY ../indexer /app/indexer

ENV PYTHONPATH=/app

CMD ["python", "-m", "scraper.main"]
