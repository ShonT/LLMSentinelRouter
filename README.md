# SentinelRouter

**Production‑Ready Local API Gateway for Budget‑Controlled LLM Routing**

SentinelRouter is a Python‑based local API gateway that sits between an autonomous agent (client) and LLM providers. Its primary purpose is to enforce strict budget control and intelligent routing between a weak model (DeepSeek) and a strong model (Anthropic Claude) based on request complexity, cumulative cost, and session‑based limits.

> **✅ Code Review & Fixes Applied (December 2025)**  
> All critical issues identified in the comprehensive code review have been fixed. See [ISSUES.md](ISSUES.md) for details on resolved bugs, security improvements, and performance enhancements.

## Features

- **Module A – Budget Kill‑Switch:** Tracks cumulative cost per session and rejects requests when `MAX_COST_PER_SESSION` is exceeded.
- **Module B – "Stingy" Judge & Categorizer:** Uses a weak model (DeepSeek) to analyze prompt complexity and recommend a route (weak/strong).
- **Module C – Dynamic Thresholding (5% Rule):** Adjusts routing strictness based on the escalation rate (percentage of requests escalated to the strong model). If the rate exceeds 5%, the threshold is raised (making the router "stingier").
- **Module D – Graph‑Based Cycle Detection:** Uses `networkx` to build a directed graph of request‑response semantic hashes and blocks repetitive cycles.
- **OpenAI‑Compatible API:** Serves a standard `/v1/chat/completions` endpoint with added headers for monitoring.
- **Structured JSON Logging & Audit Trail:** Every routing decision is logged to both the console and a JSON file, and stored in a SQLite database for post‑incident analysis.
- **Docker Container:** Production‑ready multi‑stage build based on `python:3.11‑slim`, with non‑root user, resource limits (1 CPU, 512 MB RAM), health checks, and persistent storage.

## Architecture

For a detailed design, see [documentation/architecture/overview.md](documentation/architecture/overview.md). For comprehensive documentation, visit the [documentation index](documentation/index.md).

## Quick Start

### Automated Setup (Recommended)

Run the setup script to verify all fixes and install dependencies:

```bash
chmod +x setup.sh
./setup.sh
```

This will:
- Check Python version (3.11+ required)
- Create virtual environment
- Install all dependencies
- Verify all code fixes are in place
- Guide you through next steps

### Manual Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd sentinelrouter
```

### 2. Configure Environment Variables

Copy the example environment file and fill in your API keys:

```bash
cp .env.example .env
```

Edit `.env` and set:

```bash
DEEPSEEK_API_KEY=your_deepseek_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Initialize the Database

The database will be created automatically on first run, but you can also run:

```python
from sentinelrouter.database import init_db
init_db()
```

### 5. Verify Setup

Run the verification script to ensure all fixes are applied:

```bash
python3 verify_fixes.py
```

### 6. Run Tests

```bash
pytest tests/ -v
```

### 7. Run the Server (Development)

```bash
uvicorn sentinelrouter.server:app --host 0.0.0.0 --port 8000
```

Or use Docker (Production):

```bash
docker-compose up --build
```

### 8. Send a Request

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Explain quantum computing in one sentence."}],
    "session_id": "my_session_123"
  }'
```

The response will include the standard OpenAI format plus custom headers:

- `X-Sentinel-Model-Used`: Which model served the request (deepseek or anthropic)
- `X-Sentinel-Cost`: Cost incurred for this request
- `X-Sentinel-Session-Cost`: Cumulative session cost so far
- `X-Sentinel-Complexity-Score`: Complexity score assigned by the judge (0–1)
- `X-Sentinel-Cycle-Detected`: Whether a cycle was detected (true/false)

## Project Structure

```
sentinelrouter/
├── sentinelrouter/               # Main package
│   ├── __init__.py
│   ├── server.py                 # FastAPI application
│   ├── router_logic.py           # Core routing logic (Modules A‑D)
│   ├── models.py                 # Database models (SQLAlchemy)
│   ├── database.py               # Database connection and session
│   ├── budget.py                 # Budget kill‑switch (Module A)
│   ├── judge.py                  # Stingy judge (Module B)
│   ├── threshold.py              # Dynamic thresholding (Module C)
│   ├── cycle_detector.py         # Graph‑based cycle detection (Module D)
│   ├── logging_audit.py          # Logging and audit system
│   ├── config.py                 # Configuration management
│   └── clients.py                # LLM client abstractions (DeepSeek, Anthropic)
├── tests/                        # Unit and integration tests
├── logs/                         # Directory for audit logs (auto‑created)
├── requirements.txt
├── .env.example
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Configuration

All configuration is done via environment variables. The most important ones are:

| Variable | Description | Default |
|----------|-------------|---------|
| `DEEPSEEK_API_KEY` | API key for DeepSeek (weak model) | – |
| `ANTHROPIC_API_KEY` | API key for Anthropic Claude (strong model) | – |
| `MAX_COST_PER_SESSION` | Maximum allowed cost per session (USD) | 10.0 |
| `INITIAL_THRESHOLD` | Initial complexity threshold for strong‑model escalation | 0.7 |
| `ESCALATION_RATE_LIMIT` | Target escalation rate (5% rule) | 0.05 |
| `CORS_ORIGINS` | Allowed CORS origins (comma-separated or "*" for all) | * |
| `DATABASE_URL` | SQLAlchemy database URL | `sqlite:///./data/sentinelrouter.db` |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | INFO |

See [.env.example](.env.example) for a complete list.

## Testing

Run the test suite with:

```bash
pytest tests/
```

## Docker Deployment

### Building the Image

```bash
docker build -t sentinelrouter:latest .
```

### Running with Docker Compose (Recommended)

1. Ensure you have a `.env` file with your API keys (see [Configuration](#configuration)).
2. Start the service:

   ```bash
   docker-compose up --build
   ```

   This will:
   - Build the image using the multi‑stage Dockerfile (based on `python:3.11‑slim`).
   - Run the container with a non‑root user for security.
   - Set resource limits (1 CPU, 512 MB RAM) as per the design.
   - Mount volumes for persistent storage (database and logs).
   - Expose the application on port 8000.

3. The service includes a health check at `http://localhost:8000/health`.

### Running in Production

For production deployments, consider:
   - Setting the `WORKERS` environment variable to match the number of CPU cores.
   - Using an external database (e.g., PostgreSQL) by overriding `DATABASE_URL`.
   - Setting appropriate log levels and log rotation.

### Image Details

- **Base Image**: `python:3.11‑slim` (Debian‑based, smaller than Alpine but includes necessary runtime libraries)
- **Multi‑Stage Build**: Reduces final image size by separating build and runtime dependencies.
- **Non‑Root User**: The container runs as user `sentinel` for improved security.
- **Health Check**: HTTP health check runs every 30 seconds.
- **Production ASGI Server**: Uses `gunicorn` with `uvicorn` workers (configurable via `WORKERS`).

## Monitoring Endpoints

- `GET /health` – Basic health check.
- `GET /metrics` – Prometheus‑style metrics (placeholder).
- `GET /audit/{session_id}` – Retrieve routing decisions for a session (placeholder).

## Logging

Logs are written to `logs/sentinelrouter.log` in JSON format and also printed to the console (human‑readable). Each log entry includes:

- Timestamp
- Log level
- Module and function name
- Message
- Extra structured data (when provided)

## Future Enhancements

- Support for additional LLM providers (OpenAI, Gemini, etc.)
- Real‑time dashboard for monitoring session costs and routing decisions
- Machine‑learning‑based threshold adjustment (beyond the static 5% rule)
- Prometheus metrics integration

## License

MIT