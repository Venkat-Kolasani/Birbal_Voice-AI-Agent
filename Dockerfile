# Birbal container: Render (free), or any container host. Listens on $PORT, default 7860.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    BIRBAL_DATA=/tmp/birbal/sessions \
    BIRBAL_EXPORTS=/tmp/birbal/exports

RUN pip install --no-cache-dir uv==0.12.20
WORKDIR /app

# Dependencies first (cached layer), then the app.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY server ./server
COPY web ./web

# HF runs the container as uid 1000; only /tmp needs to be writable (sessions also go to Supabase).
# Render/Railway/Koyeb inject $PORT; Hugging Face uses 7860.
EXPOSE 7860
CMD ["sh", "-c", "exec .venv/bin/uvicorn api:app --app-dir server --host 0.0.0.0 --port ${PORT:-7860}"]
