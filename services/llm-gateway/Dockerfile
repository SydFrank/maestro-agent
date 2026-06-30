# Build context = repo root (see docker-compose.yml) so we can install the
# shared `agent-common` package alongside the service.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install shared package first (changes rarely → better layer caching).
COPY packages/common /opt/common
RUN pip install /opt/common

# Install the service.
COPY services/llm-gateway/pyproject.toml ./
COPY services/llm-gateway/app ./app
RUN pip install .

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://localhost:8000/healthz'); " || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
