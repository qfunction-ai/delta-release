# Builder stage
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Dev builder — installs lint/test tools into a separate prefix
FROM builder AS dev-builder

COPY backend/requirements-dev.txt .
RUN pip install --no-cache-dir --prefix=/install-dev -r requirements-dev.txt

# Runtime stage
FROM python:3.12-slim

WORKDIR /app

# Only install runtime deps (no gcc/libpq-dev)
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Optionally copy dev packages (ruff, pytest, coverage)
# Build with --target=dev to include these
ARG INCLUDE_DEV=0
COPY --from=dev-builder /install-dev /tmp/install-dev
RUN if [ "$INCLUDE_DEV" = "1" ]; then \
      cp -a /tmp/install-dev/* /usr/local/ 2>/dev/null || true; \
    fi && \
    rm -rf /tmp/install-dev

# Copy application code
COPY backend/ .

# Copy shared package (used by both backend and eval)
COPY shared/ shared/

# Copy eval scenario YAML files (read by backend at /api/evals endpoints)
COPY evals/ /app/evals/

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    mkdir -p /data/config /data/logs && \
    chown -R appuser:appuser /app /data

USER appuser

# Expose port
EXPOSE 8000/tcp

HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
