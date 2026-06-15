FROM python:3.12-slim

WORKDIR /app

# uv installieren
RUN pip install --no-cache-dir uv

# Abhängigkeiten zuerst (Layer-Cache)
COPY pyproject.toml uv.lock ./
RUN uv sync --extra llm --extra api --no-dev --frozen

# Quellcode
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# PORT wird von Railway/Fly gesetzt; Default 8000
ENV PORT=8000

# Migrationen + Server starten
CMD uv run alembic upgrade head && \
    uv run uvicorn careapp.api.app:app \
      --host 0.0.0.0 \
      --port $PORT \
      --workers 2
