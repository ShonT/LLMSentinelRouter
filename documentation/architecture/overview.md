# Architecture Overview

SentinelRouter is a single Go process with two HTTP listeners: the API port and the dashboard port. Both listeners share the same router, config manager, SQLite store, metrics collector, and runtime model status.

## Request Flow

1. Decode an OpenAI-style chat request.
2. Resolve session defaults and session ID.
3. Load current runtime config from the config manager.
4. Apply redaction according to `REDACTION_MODE`.
5. Check semantic route cache.
6. Enforce session budget.
7. Detect prompt/response cycles.
8. Judge the prompt when requested or when smart-mode timeout requires it.
9. Apply dynamic thresholding.
10. Call provider candidates in tier order with key-instance failover.
11. Store routing decision and update metrics, semantic cache, rate limiter, and runtime model counters.

## Packages

- `internal/server`: HTTP handlers and embedded dashboard
- `internal/router`: routing pipeline and model runtime controls
- `internal/provider`: provider clients
- `internal/storage`: SQLite schema and queries
- `internal/config`: settings and config manager
- `internal/budget`: session budget logic
- `internal/judge`: judge model calls and heuristic fallback
- `internal/threshold`: dynamic threshold window
- `internal/cycle`: SimHash cycle detector
- `internal/semantic`: semantic hash and route cache
- `internal/rate`: sliding-window model limiter
- `internal/redaction`: sensitive data masking

