# MIRAGE API (fallback path: ./mirage demo --docker). Core dependencies only; no RL extra needed to serve.
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir -e .
COPY scripts ./scripts
COPY experiments ./experiments
EXPOSE 8000
CMD ["python", "scripts/serve_api.py", "--host", "0.0.0.0", "--port", "8000", "--records", "/data/records"]
