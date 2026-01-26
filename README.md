# SentinelRouter

**Production‑Ready Local API Gateway for Budget‑Controlled LLM Routing**

SentinelRouter is a Python‑based local API gateway that sits between an autonomous agent (client) and LLM providers. Its primary purpose is to enforce strict budget control and intelligent routing between a weak model (DeepSeek) and a strong model (Anthropic Claude) based on request complexity, cumulative cost, and session‑based limits.

> **✅ Code Review & Fixes Applied (December 2025)**
> All critical issues identified in the comprehensive code review have been fixed. See [documentation/operations/issues.md](documentation/operations/issues.md) for details on resolved bugs, security improvements, and performance enhancements.

## Features

- **Module A – Budget Kill‑Switch:** Tracks cumulative cost per session and rejects requests when `MAX_COST_PER_SESSION` is exceeded.
- **Module B – "Stingy" Judge & Categorizer:** Uses a weak model (DeepSeek) to analyze prompt complexity and recommend a route (weak/strong).
- **Module C – Dynamic Thresholding (5% Rule):** Adjusts routing strictness based on the escalation rate (percentage of requests escalated to the strong model). If the rate exceeds 5%, the threshold is raised (making the router "stingier").
- **Module D – Graph‑Based Cycle Detection:** Uses `networkx` to build a directed graph of request‑response semantic hashes and blocks repetitive cycles. Supports three-tiered semantic strategies: SimHash (ultra-fast), Local Vectors (balanced), and API Vectors (highest precision).
- **Semantic Similarity Strategies:** Pluggable three-tier system (SimHash/VECTORDB_LOCAL/VECTORDB_API) for detecting duplicate and paraphrased prompts with memory footprints from 5MB to 80MB.
- **Async I/O Architecture:** Built on `httpx.AsyncClient` with connection pooling (100 max connections, 20 keepalive) for high-throughput concurrent request handling without thread pool exhaustion.
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
| `GROQ_API_KEY` | API key for Groq quota-based free tier (optional) | – |
| `OPENROUTER_API_KEY` | API key for OpenRouter free-tier models (optional) | – |
| `MAX_COST_PER_SESSION` | Maximum allowed cost per session (USD) | 10.0 |
| `INITIAL_THRESHOLD` | Initial complexity threshold for strong‑model escalation | 0.7 |
| `ESCALATION_RATE_LIMIT` | Target escalation rate (5% rule) | 0.05 |
| `CORS_ORIGINS` | Allowed CORS origins (comma-separated or "*" for all) | * |
| `DATABASE_URL` | SQLAlchemy database URL | `sqlite:///./data/sentinelrouter.db` |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | INFO |

See [.env.example](.env.example) for a complete list.

## CI/CD

SentinelRouter uses GitHub Actions for PR validation, release builds, and manual staging deployments.

### Workflows

- **PR validation** (`.github/workflows/pr-validation.yml`): Runs on all pull requests. It checks formatting (Black), type checking (mypy with relaxed settings), unit tests, and integration tests (only when required secrets are present).
- **Release build** (`.github/workflows/release.yml`): Runs on pushes to `main` and tag pushes. Builds a Docker image to verify the release is buildable.
- **Staging deploy** (`.github/workflows/deploy-staging.yml`): Manual workflow for staging deployments.

### Required GitHub Secrets

Add the following repository secrets in **Settings -> Secrets and variables -> Actions**:

**Required for PR validation:**
- `DEEPSEEK_API_KEY` - DeepSeek API key for weak model
- `ANTHROPIC_API_KEY` - Anthropic API key for strong model (Claude)
- `GEMINI_BACKUP1_API_KEY` - Google Gemini API key for judge backup
- `GEMINI_BACKUP2_API_KEY` - Google Gemini API key for judge backup
- `GROQ_API_KEY` - Groq API key for alternative models
- `OPENROUTER_API_KEY` - OpenRouter API key for free-tier models

**Optional for advanced features:**
- `OPENAI_API_KEY` or `SEMANTIC_API_KEY` - Only needed if using `VECTORDB_API` semantic strategy for cycle detection

**Optional for staging deployment:**
- `STAGING_HOST` - Staging server hostname
- `STAGING_USER` - Staging server SSH user
- `STAGING_SSH_PRIVATE_KEY` - SSH private key for staging deployment

**Optional for Docker registry:**
- `DOCKER_REGISTRY` - Registry URL (e.g., `ghcr.io`)
- `DOCKER_REGISTRY_USERNAME` - Registry username
- `DOCKER_REGISTRY_PASSWORD` - Registry password or token

Integration tests in PR validation require the API keys listed above. If secrets are missing (common in forks), the integration test step is skipped. To enforce integration tests, configure the secrets in the target repository.

### Branch Protection

To require CI to pass before merging:

1. Go to **Settings -> Branches**.
2. Add a protection rule for `main`.
3. Enable **Require status checks to pass before merging**.
4. Select the **PR Validation / validate** check as a required status check.

## Supported Providers

SentinelRouter supports multiple LLM providers for flexible routing and cost optimization:

### Primary Providers
- **DeepSeek** (weak model, paid)
- **Anthropic Claude** (strong model, paid)
- **Gemini** (judge models)

### Quota-Based Free Tier Providers

#### Groq Integration
SentinelRouter supports Groq's quota-based free tier for ultra-fast inference. See [documentation/getting-started/groq-setup.md](documentation/getting-started/groq-setup.md) for details.

**Setup:**
1. Get an API key from [Groq](https://console.groq.com/)
2. Add to your `.env`:
   ```bash
   GROQ_API_KEY=your-groq-key-here
   ```

**Pre-configured Models:**
- **Llama 3.1 8B Instant** - Primary weak model (~560 tps)
- **Llama 3.3 70B Versatile** - Better reasoning (~280 tps)
- **Qwen 3 32B** - Fallback model

**Key Features:**
- Ultra-fast inference (500-1000 tokens/second)
- Quota-based (rate-limited, not billed)
- ~30 RPM free tier
- Zero cost in budget tracking

#### OpenRouter Integration
SentinelRouter also supports OpenRouter's free-tier models. See [documentation/getting-started/openrouter-setup.md](documentation/getting-started/openrouter-setup.md) for details.

**Setup:**
1. Get an API key from [OpenRouter](https://openrouter.ai/)
2. Add to your `.env`:
   ```bash
   OPENROUTER_API_KEY=your-openrouter-key-here
   ```

**Pre-configured Free Models:**
- **Llama 3.2 3B Instruct** - Small, fast
- **Mistral 7B Instruct** - Good reasoning
- **Mixtral 8x7B Instruct** - Best free model

**Rate Limits:**
- 20 requests per minute
- 200 requests per day
- 10,000 tokens per minute

These limits are configured in `config/models_config.json` and enforced by the router.

### Testing OpenRouter Integration

```bash
# With OpenRouter key set
export OPENROUTER_API_KEY=your-key-here

# Send a request (will use OpenRouter free model first)
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role":"user","content":"Hello, how are you?"}]
  }'

# Without OpenRouter key, router falls back to DeepSeek
unset OPENROUTER_API_KEY
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role":"user","content":"Hello"}]
  }'
```

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

All Rights Reserved / Usage requires written consent.
