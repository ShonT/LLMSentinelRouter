# REST API

## `GET /health`

Returns service health.

## `GET /v1/models`

Returns enabled and runtime-active models.

## `POST /v1/chat/completions`

OpenAI-compatible chat completion endpoint.

Request fields:

- `messages`: required list of `{role, content}` messages
- `session_id`: optional session identifier; generated or defaulted when omitted
- `tier`: optional `free`, `paid`, or `premium`
- `use_judge`: `true`, `false`, or omitted for smart mode
- `temperature`, `max_tokens`, `stream`

Response headers:

- `X-Sentinel-Model-Used`
- `X-Sentinel-Cost`
- `X-Sentinel-Session-Cost`
- `X-Sentinel-Complexity-Score`
- `X-Sentinel-Cycle-Detected`
- `X-Sentinel-Session-ID`

## `GET /metrics`

Returns aggregate request, session, cost, and escalation metrics.

## `GET /sessions/{session_id}`

Returns session cost and routing counts.

## `GET /audit/{session_id}`

Returns routing decisions for a session.

## Admin Policy

- `GET /api/admin/policy`
- `POST /api/admin/policy`
- `GET /api/admin/state`
- `POST /api/admin/reset-cache`
- `POST /api/admin/reset-escalation`

## Key Management

- `PUT /admin/config/keys`
- `PATCH /admin/config/keys`
- `POST /admin/config/test-key`

Key mutation and validation require `X-Admin-Token` or `Authorization: Bearer <token>` matching `ADMIN_API_TOKEN`.

