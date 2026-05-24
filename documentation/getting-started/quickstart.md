# Quickstart

## Prerequisites

- Go 1.26 or later
- Optional: Docker and Docker Compose
- Provider keys for the models configured in `config/sentinel_config.json`

## Setup

```bash
cp .env.example .env
go mod download
go test ./...
go run ./cmd/sentinelrouter
```

The API starts on `http://localhost:8000`. The dashboard starts on `http://localhost:8001` when `DASHBOARD_PORT` differs from `PORT`.

## Request

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Hello"}],
    "session_id": "quickstart"
  }'
```

## Docker

```bash
docker-compose up --build
```

