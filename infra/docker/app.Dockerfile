FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app/backend

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY backend/README.md backend/pyproject.toml backend/alembic.ini /app/backend/
COPY backend/app /app/backend/app
COPY backend/alembic /app/backend/alembic
COPY backend/assets /app/backend/assets

RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install .

COPY infra/docker/start-backend.sh /app/scripts/start-backend.sh

RUN mkdir -p /app/backend/storage /app/scripts \
    && chmod +x /app/scripts/start-backend.sh

EXPOSE 8000

CMD ["/app/scripts/start-backend.sh"]
