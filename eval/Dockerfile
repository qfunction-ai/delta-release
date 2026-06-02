# Builder stage — install deps
FROM python:3.12-slim AS builder

WORKDIR /app

COPY eval/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Runtime stage
FROM python:3.12-slim

WORKDIR /app

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY eval/app.py .
COPY shared/ shared/

# Create non-root user with write access to shared volumes
RUN useradd -m -u 1000 appuser && \
    mkdir -p /data/config /data/logs && \
    chown -R appuser:appuser /app /data

USER appuser

EXPOSE 8003/tcp

HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8003/health')" || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8003"]
