# SentinelRouter Dockerfile - Production Ready
# Multi-stage build for smaller image size

# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /app

# Install system dependencies for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsqlite3-0 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash sentinel
USER sentinel
WORKDIR /home/sentinel/app

# Copy installed packages from builder
COPY --from=builder --chown=sentinel:sentinel /root/.local /home/sentinel/.local
ENV PATH=/home/sentinel/.local/bin:$PATH

# Copy application code
COPY --chown=sentinel:sentinel . .

# Create necessary directories with proper permissions
RUN mkdir -p data logs

# Expose the port the app runs on
EXPOSE 8000

# Set environment variables for production
ENV PYTHONPATH=/home/sentinel/app
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
ENV DATABASE_URL=sqlite:////home/sentinel/app/data/sentinelrouter.db

# Health check (using httpx which is already in dependencies)
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health', timeout=2.0)" || exit 1

# Run with gunicorn for production ASGI server
# Using 2 workers (can be overridden via WORKERS environment variable)
ENTRYPOINT ["/bin/bash", "-c"]
CMD ["gunicorn --bind 0.0.0.0:8000 --worker-class uvicorn.workers.UvicornWorker --workers ${WORKERS:-2} --timeout 120 --access-logfile - sentinelrouter.sentinelrouter.server:app"]