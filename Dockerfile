FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV VITE_MIRAGE_EVALUATION=1 VITE_MIRAGE_BENCHMARKS=1
RUN npx vite build --base /

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir -e .
COPY scripts ./scripts
COPY experiments ./experiments
COPY results ./results
COPY --from=frontend /app/frontend/dist ./frontend/dist
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && git init --quiet /app \
    && git -C /app -c user.name="MIRAGE build" -c user.email="build@example.invalid" commit --allow-empty --quiet -m "container build context" \
    && python scripts/run_binder_benchmark.py --split development --per-archetype 2 --out /app/.local/benchmark-dev --benchmark-id binder-campaign-dev \
    && rm -rf /app/.git \
    && apt-get purge -y --auto-remove git \
    && rm -rf /var/lib/apt/lists/*
EXPOSE 8000
CMD ["python", "scripts/serve_web.py", "--benchmark-store", "/app/.local/benchmark-dev/binder_campaign/privileged"]
