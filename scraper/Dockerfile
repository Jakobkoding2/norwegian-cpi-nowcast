FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY scraper/ scraper/
COPY indexer/ indexer/

CMD ["python", "-m", "scraper.main"]
