FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir hatchling && pip install --no-cache-dir .

COPY scraper/ ./scraper/
COPY api/ ./api/
COPY indexer/ ./indexer/
COPY model/ ./model/

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
