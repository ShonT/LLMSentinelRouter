# SentinelRouter

SentinelRouter is a Go API gateway for budget-controlled LLM routing. It exposes an OpenAI-compatible `/v1/chat/completions` endpoint, chooses between weak and strong model tiers, tracks per-session cost in SQLite, and serves an operator dashboard on the dashboard port.

## Features

- Budget kill switch: tracks cumulative session cost and rejects requests before the configured session limit is exceeded.
- Stingy judge: optionally classifies prompt complexity and impact, with provider-backed judge models and a heuristic fallback.
- Smart mode timeout: starts with the weak tier, then calls the judge and can escalate if the weak tier exceeds `CONDITIONAL_JUDGE_TIMEOUT_SECONDS`.
- Dynamic thresholding: adjusts routing strictness against the target escalation rate.
- Cycle detection: uses SimHash over prompt/response history and forces strong-tier routing when repetitive cycles are detected.
- Semantic route cache: remembers repeated prompt patterns and can skip the judge once history is confident enough.
- Provider support: DeepSeek, Anthropic, Gemini, Groq, and OpenRouter.
- Runtime dashboard: model status, key editing/testing, routing logs, and admin policy controls.
- SQLite audit trail: sessions, routing decisions, cycle events, semantic cache tables, and aggregate metrics.
- Single Go binary: HTTP API and dashboard are served by the same executable.

## Quick Start

Run the setup script:

```bash
./setup.sh
```

Or run the steps manually:

```bash
cp .env.example .env
go mod download
go test ./...
go run ./cmd/sentinelrouter
```

Set at least one usable weak-tier key and one usable strong-tier key in `.env` before live provider calls. For the demo config, that usually means `DEEPSEEK_API_KEY` and `ANTHROPIC_API_KEY`.

The API listens on `http://localhost:8000` by default. The dashboard listens on `http://localhost:8001` when `DASHBOARD_PORT` differs from `PORT`.

## First Request

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Explain quantum computing in one sentence."}],
    "session_id": "quickstart"
  }'
```

The response is an OpenAI-style chat completion plus SentinelRouter headers:

- `X-Sentinel-Model-Used`
- `X-Sentinel-Cost`
- `X-Sentinel-Session-Cost`
- `X-Sentinel-Complexity-Score`
- `X-Sentinel-Cycle-Detected`
- `X-Sentinel-Session-ID`

## Project Layout

```text
cmd/sentinelrouter/        Main executable
internal/server/           HTTP API and embedded dashboard
internal/router/           Routing pipeline and runtime model state
internal/provider/         Provider clients
internal/storage/          SQLite persistence
internal/config/           Environment and config loading
internal/budget/           Session budget manager
internal/judge/            Prompt judge and heuristic fallback
internal/threshold/        Dynamic thresholding
internal/cycle/            SimHash cycle detection
internal/semantic/         Semantic hash and route cache
internal/rate/             Sliding-window rate limiting
internal/redaction/        Sensitive-data redaction
config/                    Demo and legacy model config files
documentation/             Project docs
```

## Configuration

Primary settings are environment variables. See `.env.example` for the full list.

| Variable | Default | Purpose |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Bind host |
| `PORT` | `8000` | API port |
| `DASHBOARD_PORT` | `8001` | Dashboard port |
| `DATABASE_URL` | `sqlite:///./data/sentinelrouter.db` | SQLite database URL |
| `SENTINEL_CONFIG_PATH` | `./config/sentinel_config.json` | Runtime config with keys, models, tiers, judge, and cache settings |
| `MODELS_CONFIG_PATH` | `./config/models_config.json` | Legacy config fallback |
| `ADMIN_API_TOKEN` | empty | Required for key mutation and key validation endpoints |
| `MAX_COST_PER_SESSION` | `10.0` | Session budget limit |
| `INITIAL_THRESHOLD` | `0.7` | Initial strong-tier threshold |
| `TARGET_ESCALATION_RATE` | `0.05` | Dynamic threshold target |
| `CONDITIONAL_JUDGE_TIMEOUT_SECONDS` | `15` | Smart-mode weak-tier timeout |
| `ENABLE_BUDGET_KILLSWITCH` | `true` | Enable session budget checks |
| `ENABLE_CYCLE_DETECTION` | `true` | Enable cycle detection |
| `ENABLE_DYNAMIC_THRESHOLD` | `true` | Enable threshold adaptation |
| `SEMANTIC_CACHE_ENABLED` | `true` | Enable route cache lookups and recording |
| `REDACTION_MODE` | `logs` | `none`, `logs`, or `strict` |

Provider base URLs can be overridden for local testing with `DEEPSEEK_BASE_URL`, `ANTHROPIC_BASE_URL`, `GEMINI_BASE_URL`, `GROQ_BASE_URL`, and `OPENROUTER_BASE_URL`.

## API Surface

- `GET /health`
- `GET /v1/models`
- `POST /v1/chat/completions`
- `GET /metrics`
- `GET /sessions/{session_id}`
- `GET /audit/{session_id}`
- `GET /api/dashboard/session-defaults`
- `POST /api/dashboard/session-defaults`
- `POST /api/dashboard/regenerate-session-id`
- `GET /api/dashboard/live`
- `GET /api/dashboard/metrics`
- `GET /api/dashboard/configuration`
- `GET /api/dashboard/logs`
- `DELETE /api/dashboard/logs`
- `POST /api/dashboard/model/{model_id}/reset-cost`
- `POST /api/dashboard/model/{model_id}/status`
- `POST /api/dashboard/reset-all-costs`
- `POST /api/dashboard/start-all`
- `POST /api/dashboard/stop-all`
- `POST /api/dashboard/models`
- `PUT /api/dashboard/models/{model_id}`
- `DELETE /api/dashboard/models/{model_id}`
- `PUT /api/dashboard/judge-config`
- `PUT /api/dashboard/routing-order`
- `GET /api/dashboard/full-config`
- `PUT/PATCH /admin/config/keys`
- `POST /admin/config/test-key`
- `GET /api/admin/policy`
- `POST /api/admin/policy`
- `GET /api/admin/state`
- `POST /api/admin/reset-cache`
- `POST /api/admin/reset-escalation`

`GET /api/dashboard/configuration` returns masked API key values. Replace or test full key values through the admin key endpoints.

## Testing

```bash
go test ./...
bash run_tests.sh --unit
bash run_tests.sh --integration
```

Integration tests use local fake provider servers and do not require live provider credentials.

## Docker

```bash
docker build -t sentinelrouter:latest .
docker-compose up --build
```

The image is a multi-stage Go build with a non-root Debian runtime. The container health check calls the Go binary's `healthcheck` subcommand.

## License

All Rights Reserved / Usage requires written consent.
