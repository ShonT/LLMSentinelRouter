# Docker Deployment Guide

SentinelRouter is designed to run in Docker for both development and production. This guide covers how to build, run, and deploy the SentinelRouter Docker image.

## Overview

The Docker setup includes:

- **Multi‑stage build** for a small production image (~200 MB).
- **Non‑root user** for security.
- **Health checks** and automatic restarts.
- **Persistent volumes** for database and logs.
- **Resource limits** (1 CPU, 512 MB RAM) to prevent resource exhaustion.
- **Docker Compose** for easy orchestration.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (version 20.10+)
- [Docker Compose](https://docs.docker.com/compose/install/) (optional, but recommended)
- API keys for DeepSeek, Anthropic, and (optionally) Gemini.

## Quick Start

### Using Docker Run

1. **Build the image:**

   ```bash
   docker build -t sentinelrouter:latest .
   ```

2. **Create a `.env` file** with your API keys (see [Configuration](configuration.md)).

3. **Run the container:**

   ```bash
   docker run -d \
     --name sentinelrouter \
     --env-file .env \
     -p 8000:8000 \
     -p 8001:8001 \
     sentinelrouter:latest
   ```

4. **Verify the container is healthy:**

   ```bash
   docker logs sentinelrouter
   curl http://localhost:8000/health
   ```

### Using Docker Compose (Recommended)

1. **Create `.env` file** in the project root:

   ```bash
   DEEPSEEK_API_KEY=sk-...
   ANTHROPIC_API_KEY=sk-ant-...
   GEMINI_BACKUP1_API_KEY=AIza...
   GEMINI_BACKUP2_API_KEY=AIza...
   # Optional overrides (see below)
   ```

2. **Start the service:**

   ```bash
   docker-compose up -d
   ```

3. **Check status:**

   ```bash
   docker-compose ps
   docker-compose logs -f
   ```

4. **Stop the service:**

   ```bash
   docker-compose down
   ```

   To also remove persistent volumes (deletes all data):

   ```bash
   docker-compose down -v
   ```

## Image Details

### Build Stages

The `Dockerfile` uses two stages:

1. **Builder stage** (`python:3.11‑slim`):
   - Installs build dependencies (gcc, python‑dev).
   - Installs Python packages into `/root/.local`.

2. **Runtime stage** (`python:3.11‑slim`):
   - Copies installed packages from builder.
   - Creates a non‑root user `sentinel`.
   - Sets up directories and permissions.
   - Defines health check and entrypoint.

### Security Features

- **Non‑root user**: The container runs as user `sentinel` (UID 1000).
- **Minimal base image**: Based on `python:3.11‑slim`, with only essential runtime libraries.
- **No sensitive data in layers**: API keys are provided via environment variables or `.env` file, not baked into the image.
- **Resource limits**: CPU and memory limits are enforced via Docker Compose or runtime flags.

## Persistent Storage

By default, Docker Compose creates two named volumes:

| Volume | Container Path | Purpose |
|--------|----------------|---------|
| `sentinelrouter_data` | `/home/sentinel/app/data` | SQLite database, configuration cache, metrics. |
| `sentinelrouter_logs` | `/home/sentinel/app/logs` | Application logs (`sentinelrouter.log`). |

### Using Host Directories (Development)

If you prefer to mount host directories for easier debugging, modify `docker‑compose.yml`:

```yaml
volumes:
  - ./data:/home/sentinel/app/data
  - ./logs:/home/sentinel/app/logs
```

**Note**: On Linux, you may need to adjust permissions because the container runs as user `sentinel`. The container automatically creates the directories with the correct ownership.

## Environment Variables

All configuration can be supplied via environment variables. The following table lists the most important ones; see `.env.example` for a complete list.

| Variable | Default | Description |
|----------|---------|-------------|
| `DEEPSEEK_API_KEY` | (required) | DeepSeek API key for weak‑model routing. |
| `ANTHROPIC_API_KEY` | (required) | Anthropic API key for strong‑model routing. |
| `GEMINI_BACKUP1_API_KEY` | `<REDACTED>` | Gemini API key for backup judge 1. |
| `GEMINI_BACKUP2_API_KEY` | `<REDACTED>` | Gemini API key for backup judge 2 (primary judge). |
| `WEAK_MODEL_ID` | `deepseek‑chat` | Model ID for the weak tier (used when judge is off). |
| `STRONG_MODEL_ID` | `claude‑3‑haiku‑20240307` | Model ID for the strong tier. |
| `MAX_COST_PER_SESSION` | `25.0` | Maximum cost (USD) per session before budget kill‑switch triggers. |
| `COMPLEXITY_THRESHOLD` | `0.5` | Initial complexity threshold for judge decisions. |
| `TARGET_ESCALATION_RATE` | `0.05` | Target escalation rate (5 %) for dynamic threshold adjustment. |
| `DATABASE_URL` | `sqlite:////home/sentinel/app/data/sentinelrouter.db` | Database connection URL. |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `WORKERS` | `2` | Number of Gunicorn worker processes. |
| `ENABLE_BUDGET_KILLSWITCH` | `true` | Enable/disable Module A (budget kill‑switch). |
| `ENABLE_CYCLE_DETECTION` | `true` | Enable/disable Module D (cycle detection). |
| `ENABLE_DYNAMIC_THRESHOLD` | `true` | Enable/disable Module C (dynamic thresholding). |

## Health Checks

Both the Docker image and Docker Compose define a health check that probes the `/health` endpoint every 30 seconds.

- **Interval**: 30 s
- **Timeout**: 3 s
- **Start period**: 5 s
- **Retries**: 3

If the health check fails three times, the container is marked as unhealthy. Docker Compose will restart the container if the restart policy is set to `unless‑stopped` (default).

You can manually check the health:

```bash
docker inspect --format='{{.State.Health.Status}}' sentinelrouter
```

## Resource Limits

The Docker Compose configuration includes resource limits to prevent the container from consuming excessive CPU or memory:

```yaml
deploy:
  resources:
    limits:
      cpus: '1.0'
      memory: 512M
```

These limits match the design specifications. You can adjust them in `docker‑compose.yml` for your deployment environment.

## Production Deployment

### 1. Use a Reverse Proxy

In production, you should place SentinelRouter behind a reverse proxy (e.g., nginx, Traefik, Caddy) for:

- **SSL/TLS termination**
- **Rate limiting**
- **IP whitelisting**
- **Load balancing** (if scaling horizontally)

Example nginx configuration snippet:

```nginx
server {
    listen 443 ssl;
    server_name sentinelrouter.example.com;

    ssl_certificate /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /dashboard {
        proxy_pass http://localhost:8001;
        proxy_set_header Host $host;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### 2. Secrets Management

For production, avoid storing API keys in plain‑text `.env` files. Use a secrets manager:

- **Docker Swarm Secrets**
- **Kubernetes Secrets**
- **HashiCorp Vault**
- **AWS Secrets Manager**

Example with Docker Compose and secrets (Docker Swarm):

```yaml
services:
  sentinelrouter:
    ...
    secrets:
      - deepseek_api_key
      - anthropic_api_key

secrets:
  deepseek_api_key:
    external: true
  anthropic_api_key:
    external: true
```

### 3. Monitoring and Logging

- **Log aggregation**: Use Docker’s logging driver to forward logs to ELK, Loki, or CloudWatch.
- **Metrics**: The dashboard exposes Prometheus‑format metrics at `/dashboard/api/v1/metrics`.
- **Alerting**: Set up alerts for budget exceedance, health‑check failures, or high error rates.

### 4. Database Considerations

The default SQLite database is suitable for light to medium loads. For high‑concurrency production deployments, consider switching to PostgreSQL:

1. Change `DATABASE_URL` to a PostgreSQL connection string.
2. Use a separate PostgreSQL container (or managed service).
3. Update `requirements.txt` to include `psycopg2‑binary` and adjust `database.py` accordingly.

## Troubleshooting

### Container Fails to Start

- **Check logs**: `docker logs sentinelrouter`
- **Common issues**:
  - Missing API keys (environment variables).
  - Port conflict (8000 or 8001 already in use).
  - Permission issues with mounted volumes.

### Health Check Fails

- Ensure the server is up: `curl http://localhost:8000/health`
- Verify the container is running: `docker ps`
- Increase the start period if the server takes longer to initialize.

### Performance Issues

- Increase `WORKERS` (but stay within CPU limits).
- Consider moving the database to a faster storage (SSD) or using PostgreSQL.
- Enable semantic cache (`ENABLE_SEMANTIC_CACHE=true`) to reduce repeated LLM calls.

## Upgrading

To upgrade to a newer version:

1. Pull the latest code (or rebuild the image).
2. Stop the existing container:

   ```bash
   docker-compose down
   ```

3. Rebuild (if using local build):

   ```bash
   docker-compose build --no-cache
   ```

4. Start the new version:

   ```bash
   docker-compose up -d
   ```

The persistent volumes ensure that your database and logs survive the upgrade.

## Further Reading

- [Configuration Guide](configuration.md) – Detailed explanation of all configuration options.
- [Architecture Overview](../architecture/overview.md) – Understanding the internal components.
- [Dashboard Guide](../api-reference/dashboard-api.md) – Using the built‑in dashboard for monitoring.

---

*Last updated: 2025‑12‑14*