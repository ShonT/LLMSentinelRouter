# REST API Reference

## Overview

SentinelRouter provides an OpenAI‑compatible REST API for chat completions, extended with budget‑aware routing, session management, and custom monitoring headers. All endpoints are served on port 8000 by default.

## Base URL

```
http://localhost:8000
```

## Authentication

No authentication is required by default. For production deployments, you can enable API‑key authentication via the `REQUIRE_API_KEY` environment variable.

## Endpoints

### POST `/v1/chat/completions`

The primary endpoint for chat completions. Accepts a standard OpenAI‑style request and returns a completion with added SentinelRouter headers.

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `messages` | Array | Yes | List of message objects (role, content) |
| `model` | String | No | **Ignored** – SentinelRouter chooses the model automatically |
| `session_id` | String | Yes | Unique identifier for cost tracking and session management |
| `temperature` | Number | No | Controls randomness (0.0–2.0) |
| `max_tokens` | Number | No | Maximum tokens to generate |
| `stream` | Boolean | No | Whether to stream the response (not yet supported) |

##### Example Request

```json
{
  "messages": [
    {"role": "user", "content": "Explain quantum computing in one sentence."}
  ],
  "session_id": "my_session_123",
  "temperature": 0.7,
  "max_tokens": 500
}
```

#### Response

Returns a standard OpenAI chat‑completion object with additional custom headers.

##### Response Headers

| Header | Description |
|--------|-------------|
| `X-Sentinel-Model-Used` | Model that processed the request (e.g., `deepseek-chat`, `claude-3-5-sonnet`) |
| `X-Sentinel-Cost` | Cost incurred for this request (USD) |
| `X-Sentinel-Session-Cost` | Cumulative session cost so far (USD) |
| `X-Sentinel-Complexity-Score` | Complexity score assigned by the judge (0.0–1.0) |
| `X-Sentinel-Cycle-Detected` | Whether a semantic‑hash cycle was detected (`true`/`false`) |
| `X-Sentinel-Session-ID` | The session identifier used for the request |

##### Response Body Example

```json
{
  "id": "chatcmpl-123",
  "object": "chat.completion",
  "created": 1734168350,
  "model": "claude-3-5-sonnet",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Quantum computing uses quantum bits to perform calculations that would be infeasible for classical computers."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 25,
    "total_tokens": 35
  }
}
```

#### Error Responses

| Status Code | Error Code | Description |
|-------------|------------|-------------|
| 400 | `missing_session_id` | `session_id` field is missing |
| 402 | `budget_exceeded` | Session cost exceeds `MAX_COST_PER_SESSION` |
| 429 | `rate_limit_exceeded` | Rate limit for the selected model has been reached |
| 500 | `judge_failed` | All judge models failed to respond |
| 500 | `no_available_models` | No models are available for routing |
| 500 | `internal_error` | Unexpected server error |

### GET `/health`

Simple health check endpoint.

**Response:**

```json
{
  "status": "healthy",
  "timestamp": "2025-12-14T10:25:45.982Z"
}
```

### GET `/metrics`

Returns aggregate system statistics.

**Response:**

```json
{
  "requests_total": 1250,
  "sessions_total": 45,
  "cost_total": 12.34,
  "escalation_rate": 0.15,
  "strong_requests": 188,
  "weak_requests": 1062
}
```

### GET `/sessions/{session_id}`

Retrieve session‑specific metrics.

**Response:**

```json
{
  "session_id": "session_abc123",
  "client_ip": "192.168.1.1",
  "created_at": "2025-12-14T10:25:45.982Z",
  "max_cost_per_session": 5.0,
  "current_cost": 2.345,
  "is_active": true,
  "total_requests": 25,
  "strong_requests": 5,
  "weak_requests": 20,
  "escalation_rate": 0.2
}
```

### GET `/audit/{session_id}`

Retrieve detailed routing decisions for a session.

**Response:**

```json
{
  "session_id": "session_abc123",
  "decisions": [
    {
      "request_id": "req_xyz789",
      "timestamp": "2025-12-14T10:25:45.982Z",
      "model_used": "claude-3-5-sonnet",
      "complexity_score": 0.82,
      "cost_incurred": 0.035,
      "impact_scope": "HIGH",
      "reason": "Complexity threshold exceeded (0.82 > 0.65)"
    }
  ]
}
```

## Request Examples

### cURL

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Hello"}],
    "session_id": "test_session_1"
  }'
```

### Python (requests)

```python
import requests

response = requests.post(
    "http://localhost:8000/v1/chat/completions",
    json={
        "messages": [{"role": "user", "content": "Hello"}],
        "session_id": "test_session_1"
    }
)

print(f"Model used: {response.headers['X-Sentinel-Model-Used']}")
print(f"Cost: ${response.headers['X-Sentinel-Cost']}")
```

### JavaScript (fetch)

```javascript
fetch('http://localhost:8000/v1/chat/completions', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    messages: [{role: 'user', content: 'Hello'}],
    session_id: 'test_session_1'
  })
})
  .then(response => {
    console.log('Model:', response.headers.get('X-Sentinel-Model-Used'));
    return response.json();
  })
  .then(data => console.log(data));
```

## Rate Limiting

SentinelRouter enforces rate limits per model based on the configured `free_tier_limits` and `paid_tier_limits`. When a limit is exceeded, the request is automatically routed to the next available model in the priority group. If all models in a group are rate‑limited, the endpoint returns a 429 error.

## Session Management

Each request must include a `session_id`. The server tracks cumulative costs per session and enforces the `MAX_COST_PER_SESSION` budget (default: $10.00). When the budget is exceeded, subsequent requests receive a 402 error.

## Related Documentation

- [Headers and Metrics](headers-and-metrics.md) – Detailed explanation of custom headers and metrics endpoints.
- [Dashboard API](dashboard-api.md) – Real‑time monitoring and configuration dashboard (port 8001).
- [Configuration Guide](../getting-started/configuration.md) – How to configure API behavior.

---

**Last Updated:** December 15, 2025  
**Version:** SentinelRouter v1.0