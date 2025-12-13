# Proposal: Background Scheduler for Pending Work

## Summary
Add a scheduler component to pick up and process pending tasks (e.g., long-running requests, retries, model health checks, cache population tasks). The scheduler can run as an internal thread/process or as a separate microservice.

## Responsibilities
- Retry failed background tasks (e.g., judge evaluations that previously failed)
- Pre-warm cache entries by sampling requests
- Perform periodic health checks on model providers and update Model-State Server
- Recompute routing order based on aggregated metrics

## Design Notes
- Use a simple job queue (SQLite-backed or Redis) for persistence
- Provide retry/backoff policies, idempotency keys, and visibility into queue status
- Expose metrics for queue length, success/failure rates

## Acceptance Criteria
- Scheduler can enqueue and process tasks reliably
- Dashboard shows pending/processing/completed tasks
- Secure and rate-limited operations

## Status
Planned (issue filed for later implementation)
