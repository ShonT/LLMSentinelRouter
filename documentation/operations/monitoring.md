# Monitoring

## Health

`GET /health` returns basic liveness.

The Docker health check runs:

```bash
sentinelrouter healthcheck
```

## Metrics

`GET /metrics` returns aggregate JSON metrics:

- `requests_total`
- `sessions_total`
- `cost_total`
- `escalation_rate`
- `strong_requests`
- `weak_requests`

The dashboard also reads recent routing and latency metrics from the Go metrics collector and SQLite routing decisions.

## Audit

`GET /audit/{session_id}` returns stored routing decisions for a session.

SQLite data lives under `data/` by default. Configure `DATABASE_URL` for another path.

