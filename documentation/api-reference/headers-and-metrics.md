# Headers and Metrics

## Overview

SentinelRouter provides extensive observability through custom response headers and dedicated metrics endpoints. These features allow you to monitor routing decisions, track costs, and understand system performance without parsing response content.

## Custom Headers

Every successful response from the `/v1/chat/completions` endpoint includes custom headers that provide detailed routing information. These headers follow the `X-Sentinel-*` naming convention and can be used for logging, monitoring, and cost tracking.

### Available Headers

| Header | Description | Example Value |
|--------|-------------|---------------|
| `X-Sentinel-Model-Used` | The actual LLM model that processed the request | `deepseek-chat`, `gemini-1.5-flash`, `claude-3-5-sonnet` |
| `X-Sentinel-Cost` | Cost incurred for this specific request (in USD) | `0.0015` |
| `X-Sentinel-Session-Cost` | Cumulative cost for the current session (in USD) | `2.345` |
| `X-Sentinel-Complexity-Score` | Judge-assigned complexity score (0.0-1.0) | `0.72` |
| `X-Sentinel-Cycle-Detected` | Whether the cycle detector identified a repeated request | `true`, `false` |
| `X-Sentinel-Session-ID` | The session identifier used for this request | `session_abc123` |

### Example Response Headers

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Sentinel-Model-Used: claude-3-5-sonnet
X-Sentinel-Cost: 0.035
X-Sentinel-Session-Cost: 1.245
X-Sentinel-Complexity-Score: 0.82
X-Sentinel-Cycle-Detected: false
X-Sentinel-Session-ID: ip_192.168.1.1_a1b2c3d4

{
  "id": "chatcmpl-123",
  "object": "chat.completion",
  "created": 1734168350,
  "model": "claude-3-5-sonnet",
  "choices": [...],
  "usage": {...}
}
```

### Using Headers in Applications

#### JavaScript (Fetch API)
```javascript
async function sendRequest() {
  const response = await fetch('http://localhost:8000/v1/chat/completions', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      messages: [{role: 'user', content: 'Hello'}],
      session_id: 'my_session'
    })
  });
  
  const cost = response.headers.get('X-Sentinel-Cost');
  const model = response.headers.get('X-Sentinel-Model-Used');
  console.log(`Request cost: $${cost}, Model: ${model}`);
  
  const data = await response.json();
  // ... process data
}
```

#### Python (requests)
```python
import requests

response = requests.post(
    'http://localhost:8000/v1/chat/completions',
    json={'messages': [{'role': 'user', 'content': 'Hello'}]}
)

print(f"Model used: {response.headers['X-Sentinel-Model-Used']}")
print(f"Cost: ${response.headers['X-Sentinel-Cost']}")
print(f"Complexity: {response.headers['X-Sentinel-Complexity-Score']}")
```

#### cURL
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Hello"}]}' \
  -i  # Include headers in output
```

## System Metrics Endpoint

The `/metrics` endpoint provides aggregate system statistics for monitoring and alerting.

### GET `/metrics`

Returns current system metrics including request counts, costs, and escalation rates.

**Response Format:**
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

**Field Descriptions:**

| Field | Description | Calculation |
|-------|-------------|-------------|
| `requests_total` | Total number of routing decisions recorded | Count of all rows in `routing_decisions` table |
| `sessions_total` | Total number of unique sessions | Count of all rows in `sessions` table |
| `cost_total` | Total cost across all sessions (USD) | Sum of `current_cost` in `sessions` table |
| `escalation_rate` | Percentage of requests that used strong models | `strong_requests / requests_total` |
| `strong_requests` | Number of requests routed to strong models | Count where `model_used` is "anthropic" or other strong models |
| `weak_requests` | Number of requests routed to weak models | `requests_total - strong_requests` |

### Example Usage

```bash
# Get current metrics
curl http://localhost:8000/metrics

# Parse specific metric with jq
curl -s http://localhost:8000/metrics | jq '.cost_total'
```

## Session Metrics

SentinelRouter provides detailed session-level metrics for tracking individual user or application usage.

### GET `/sessions/{session_id}`

Retrieves detailed metrics for a specific session.

**Parameters:**
- `session_id` (path): The session identifier

**Response Format:**
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

**Field Descriptions:**

| Field | Description | Source |
|-------|-------------|--------|
| `session_id` | Unique session identifier | From session table |
| `client_ip` | Client IP address (if recorded) | From session table |
| `created_at` | Session creation timestamp | From session table |
| `max_cost_per_session` | Budget limit for this session (USD) | From session table or config |
| `current_cost` | Cumulative cost for this session (USD) | From session table |
| `is_active` | Whether the session is still active | From session table |
| `total_requests` | Total requests in this session | Count of routing decisions |
| `strong_requests` | Strong model requests in this session | Filter by model type |
| `weak_requests` | Weak model requests in this session | `total_requests - strong_requests` |
| `escalation_rate` | Session-specific escalation rate | `strong_requests / total_requests` |

### Example: Monitoring Session Budget

```python
import requests

def check_session_budget(session_id):
    """Check if a session is approaching its budget limit."""
    response = requests.get(f'http://localhost:8000/sessions/{session_id}')
    data = response.json()
    
    budget_used = data['current_cost'] / data['max_cost_per_session']
    
    if budget_used > 0.9:
        print(f"WARNING: Session {session_id} has used {budget_used:.0%} of budget")
        return False
    return True
```

## Audit Trail

For debugging and compliance, SentinelRouter maintains a detailed audit trail of routing decisions.

### GET `/audit/{session_id}`

Retrieves all routing decisions for a specific session.

**Parameters:**
- `session_id` (path): The session identifier

**Response Format:**
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
    },
    {
      "request_id": "req_abc456",
      "timestamp": "2025-12-14T10:24:30.123Z",
      "model_used": "deepseek-chat",
      "complexity_score": 0.42,
      "cost_incurred": 0.0015,
      "impact_scope": "LOW",
      "reason": "Routine question, using weak model"
    }
  ]
}
```

**Decision Field Descriptions:**

| Field | Description |
|-------|-------------|
| `request_id` | Unique identifier for the request |
| `timestamp` | When the decision was made |
| `model_used` | Which model processed the request |
| `complexity_score` | Judge-assigned complexity (0.0-1.0) |
| `cost_incurred` | Cost for this specific request (USD) |
| `impact_scope` | Judge-assigned impact category (LOW, MEDIUM, HIGH) |
| `reason` | Human-readable explanation of routing decision |

### Example: Analyzing Audit Data

```python
import requests
import pandas as pd

def analyze_session_decisions(session_id):
    """Analyze routing decisions for a session."""
    response = requests.get(f'http://localhost:8000/audit/{session_id}')
    data = response.json()
    
    # Convert to DataFrame for analysis
    df = pd.DataFrame(data['decisions'])
    
    # Calculate statistics
    avg_complexity = df['complexity_score'].mean()
    total_cost = df['cost_incurred'].sum()
    strong_model_percentage = (df['model_used'].str.contains('claude|gpt-4')).mean() * 100
    
    print(f"Session {session_id}:")
    print(f"  Average complexity: {avg_complexity:.2f}")
    print(f"  Total cost: ${total_cost:.3f}")
    print(f"  Strong model usage: {strong_model_percentage:.1f}%")
    
    return df
```

## Dashboard Metrics

The enhanced dashboard (port 8001) provides additional real-time metrics not available through the main API.

### Key Dashboard Metrics

| Metric | Description | Dashboard Endpoint |
|--------|-------------|-------------------|
| Judge Success Rate | Percentage of successful judge calls | `/api/dashboard/metrics` |
| Judge Skip Rate | Percentage of requests where judge was skipped | `/api/dashboard/metrics` |
| Latency Trends | Historical latency for judge/weak/strong models | `/api/dashboard/metrics` |
| Fallback Chain | Recent judge fallback events | `/api/dashboard/metrics` |
| Model RPM | Real-time requests per minute per model | `/api/dashboard/live` |

### Example: Fetching Dashboard Metrics

```python
import requests

def get_dashboard_metrics():
    """Fetch comprehensive metrics from dashboard."""
    response = requests.get('http://localhost:8001/api/dashboard/metrics')
    metrics = response.json()
    
    return {
        'judge_success_rate': metrics['judge_success_rate'],
        'total_fallbacks': metrics['total_fallbacks'],
        'avg_judge_latency': metrics['judge_latency']['avg_ms']
    }
```

## Cost Tracking

### Understanding Cost Headers

SentinelRouter provides two cost-related headers:

1. **`X-Sentinel-Cost`**: Cost of the current request only
2. **`X-Sentinel-Session-Cost`**: Cumulative cost for the entire session

These costs are calculated based on:
- Model-specific pricing (from `config/models_config.json`)
- Token counts (when available)
- Tier-based pricing adjustments

### Example Cost Calculation

```python
# Example cost calculation for a request
def estimate_cost(model_used, input_tokens, output_tokens, tier='free'):
    """Estimate cost based on model and token counts."""
    pricing = {
        'deepseek-chat': {'input': 0.14, 'output': 0.28},  # per million tokens
        'claude-3-5-sonnet': {'input': 3.0, 'output': 15.0},
        'gemini-1.5-flash': {'input': 0.075, 'output': 0.30}
    }
    
    if model_used not in pricing:
        return 0.0
    
    input_cost = (input_tokens / 1_000_000) * pricing[model_used]['input']
    output_cost = (output_tokens / 1_000_000) * pricing[model_used]['output']
    
    # Apply tier discount
    tier_discount = {'free': 1.0, 'paid': 0.9, 'premium': 0.8}
    discount = tier_discount.get(tier, 1.0)
    
    return (input_cost + output_cost) * discount
```

## Monitoring and Alerting

### Creating Alerts with Headers

You can create monitoring rules based on response headers:

```python
from typing import Dict

def check_headers_for_alerts(headers: Dict[str, str]) -> list:
    """Check response headers for potential issues."""
    alerts = []
    
    # High complexity alert
    complexity = float(headers.get('X-Sentinel-Complexity-Score', 0))
    if complexity > 0.8:
        alerts.append(f"High complexity score: {complexity}")
    
    # High cost alert
    cost = float(headers.get('X-Sentinel-Cost', 0))
    if cost > 0.05:  # $0.05 per request threshold
        alerts.append(f"High request cost: ${cost}")
    
    # Cycle detection alert
    if headers.get('X-Sentinel-Cycle-Detected', 'false') == 'true':
        alerts.append("Cycle detected - repeated request")
    
    return alerts
```

### Setting Up Prometheus Metrics

You can expose SentinelRouter metrics to Prometheus by creating a custom exporter:

```python
from prometheus_client import Counter, Gauge, start_http_server

# Define metrics
REQUEST_COST = Gauge('sentinel_request_cost', 'Cost per request', ['model', 'session'])
SESSION_COST = Gauge('sentinel_session_cost', 'Cumulative session cost', ['session'])
COMPLEXITY_SCORE = Gauge('sentinel_complexity_score', 'Request complexity score')

def process_response(response):
    """Extract metrics from response and expose to Prometheus."""
    model = response.headers['X-Sentinel-Model-Used']
    session = response.headers['X-Sentinel-Session-ID']
    cost = float(response.headers['X-Sentinel-Cost'])
    complexity = float(response.headers['X-Sentinel-Complexity-Score'])
    
    # Update metrics
    REQUEST_COST.labels(model=model, session=session).set(cost)
    COMPLEXITY_SCORE.set(complexity)

# Start Prometheus metrics server
start_http_server(8002)
```

## Best Practices

### 1. **Log Headers for Analysis**
Always log the custom headers to analyze routing patterns and costs:
```python
import logging

logger = logging.getLogger(__name__)

def log_routing_details(response):
    headers = response.headers
    logger.info(
        f"Model: {headers['X-Sentinel-Model-Used']}, "
        f"Cost: ${headers['X-Sentinel-Cost']}, "
        f"Complexity: {headers['X-Sentinel-Complexity-Score']}"
    )
```

### 2. **Set Budget Alerts**
Use session cost headers to implement budget alerts:
```python
def check_budget(session_id, response):
    session_cost = float(response.headers['X-Sentinel-Session-Cost'])
    if session_cost > 4.5:  # Near $5.00 budget
        send_alert(f"Session {session_id} approaching budget: ${session_cost}")
```

### 3. **Monitor Escalation Rates**
Regularly check system metrics to ensure appropriate escalation rates:
```bash
# Daily escalation rate check
curl -s http://localhost:8000/metrics | jq '.escalation_rate'
```

### 4. **Use Audit Trail for Debugging**
When users report issues, check the audit trail to understand routing decisions:
```python
def debug_session(session_id):
    decisions = requests.get(f'http://localhost:8000/audit/{session_id}').json()
    for decision in decisions['decisions'][-10:]:  # Last 10 decisions
        print(f"{decision['timestamp']}: {decision['model_used']} - {decision['reason']}")
```

## Troubleshooting

### Common Issues

| Issue | Possible Cause | Solution |
|-------|---------------|----------|
| Missing headers | Request didn't go through routing logic | Ensure you're using `/v1/chat/completions` endpoint |
| Incorrect costs | Pricing configuration outdated | Update `config/models_config.json` |
| High escalation rate | Judge threshold too low | Adjust `judge.threshold` in configuration |
| No session metrics | Session ID not found | Verify session exists in database |

### Debugging with Headers

When debugging routing issues, check these headers in order:

1. `X-Sentinel-Model-Used` - Which model was actually called
2. `X-Sentinel-Complexity-Score` - Why that model was chosen
3. `X-Sentinel-Cycle-Detected` - Whether semantic cache was used
4. `X-Sentinel-Cost` - Whether cost expectations match

## Related Documentation

- [REST API Reference](rest-api.md) - Complete API endpoint documentation
- [Dashboard API Reference](dashboard-api.md) - Real-time monitoring dashboard
- [Configuration Guide](../getting-started/configuration.md) - Configuring metrics and costs
- [Architecture Overview](../architecture/overview.md) - How metrics are collected and tracked

---

**Next Steps**:
- Explore the [Testing](../development/testing.md) documentation for metrics validation
- Learn about [Troubleshooting](../operations/troubleshooting.md) common metrics issues
- Review [Backup and Recovery](../operations/backup-and-recovery.md) for metrics data preservation