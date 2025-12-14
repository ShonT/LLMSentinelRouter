# Dashboard API Reference

## Overview

The SentinelRouter Dashboard is a separate FastAPI application that provides a rich, real-time web interface for monitoring and managing the routing system. It runs alongside the main API server and offers three specialized tabs:

1. **Live Traffic** - Real-time model metrics, performance charts, and system health
2. **Configuration & Keys** - API key management, model priority configuration, and rate limiting
3. **Router Logic** - Strong model escalation logs and routing decision diagnostics

## Accessing the Dashboard

The dashboard runs on port **8001** by default, while the main API runs on port 8000.

| Environment | URL | Default Credentials |
|-------------|-----|---------------------|
| Local Development | [http://localhost:8001](http://localhost:8001) | None (public access) |
| Docker Deployment | [http://localhost:8001](http://localhost:8001) | None (public access) |
| Production | Configure via `CORS_ORIGINS` environment variable | None (recommend reverse proxy authentication) |

> **Security Note**: The dashboard is publicly accessible by default. For production deployments, it's recommended to:
> - Use a reverse proxy with authentication (e.g., Basic Auth, OAuth)
> - Configure `CORS_ORIGINS` to restrict origins
> - Run behind a VPN or internal network

## Dashboard Architecture

The dashboard is built as a separate FastAPI application (`sentinelrouter/sentinelrouter/dashboard.py`) that:

- Serves a single-page HTML/JavaScript application with three tabs
- Provides RESTful API endpoints for each tab's data
- Shares the same database and configuration as the main server
- Runs in the same process (separate thread) when started via `server.py`

```python
# Starting the dashboard (automatically done by server.py)
from sentinelrouter.dashboard import start_dashboard_server
start_dashboard_server(host="0.0.0.0", port=8001)
```

## Tab 1: Live Traffic

The Live Traffic tab provides real-time monitoring of model performance and system metrics.

### Key Features

- **Model Status Grid**: Real-time cards showing each model's:
  - Requests per minute (RPM)
  - Daily request count vs. limit
  - Session cost accumulation
  - Active/inactive/disabled status
- **Performance Charts**:
  - Latency trends for judge, weak, and strong models (last 50 requests)
  - Per-judge breakdown with success rates and call counts
  - Fallback chain visualization
- **Global Controls**:
  - Reset all session costs
  - Emergency stop/start all models
  - Individual model cost reset

### Data Sources

The Live Traffic tab fetches data from two main endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/dashboard/live` | GET | Returns live model state and configuration |
| `/api/dashboard/metrics` | GET | Returns performance metrics and chart data |

### Example Live Data Response

```json
{
  "models": [
    {
      "id": "deepseek-chat",
      "config": {
        "display_name": "DeepSeek Chat",
        "status": "active",
        "limits": {
          "requests_per_minute": 15,
          "requests_per_day": 1500
        },
        "pricing": {
          "usage_tiers": [...]
        }
      },
      "state": {
        "current_rpm": 8.2,
        "requests_today": 342,
        "total_cost_session": 0.45,
        "last_updated_ts": "2025-12-14T10:25:45.982Z"
      }
    }
  ]
}
```

## Tab 2: Configuration & Keys

The Configuration tab allows administrators to manage API keys, model priority, and pricing tiers.

### Sections

1. **API Keys Management**
   - View masked API keys for all supported providers
   - Reveal keys temporarily (requires security confirmation)
   - Update keys via environment variables (requires server restart)

2. **Model Priority & Ordering**
   - Drag-and-drop interface to change routing priority
   - Visual indication of priority groups (`fast_tier`, `balanced_tier`, `cost_sensitive`)
   - Real-time order updates

3. **Rate Limit Settings**
   - Adjust requests-per-minute per model
   - Set daily request limits
   - Configure tier-based throttling

4. **Pricing Tiers**
   - Define usage-based pricing tiers
   - Set threshold requests and cost per million tokens
   - Add/delete pricing tiers

### Configuration Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/dashboard/configuration` | GET | Returns current configuration including API keys |
| `/api/dashboard/full-config` | GET | Returns complete configuration (including judge and routing order) |
| `/api/dashboard/models` | POST | Create a new model configuration |
| `/api/dashboard/models/{model_id}` | PUT | Update an existing model configuration |
| `/api/dashboard/models/{model_id}` | DELETE | Delete a model configuration |
| `/api/dashboard/judge-config` | PUT | Update judge configuration |
| `/api/dashboard/routing-order` | PUT | Update routing order configuration |

### Example Configuration Update

```bash
# Update a model's status
curl -X POST "http://localhost:8001/api/dashboard/model/deepseek-chat/status" \
  -H "Content-Type: application/json" \
  -d '{"status": "disabled"}'
```

## Tab 3: Router Logic

The Router Logic tab provides detailed logs of strong model escalations and routing decisions.

### Features

- **Filterable Logs**: View only strong model escalations or all routing decisions
- **Decision Details**: Each log entry shows:
  - Model used and timestamp
  - Complexity score and impact scope
  - Cost incurred and cycle detection status
  - Decision reason
- **Request/Response Preview**: View truncated request and response content (if enabled)
- **Real-time Updates**: Logs refresh every 10 seconds

### Log Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/dashboard/logs` | GET | Retrieve recent routing decision logs |
| `/api/dashboard/logs` | DELETE | Clear all routing logs (demo purposes) |

### Example Log Entry

```json
{
  "session_id": "session_abc123",
  "request_id": "req_xyz789",
  "model_used": "claude-3-5-sonnet",
  "complexity_score": 0.82,
  "cost_incurred": 0.035,
  "impact_scope": "HIGH",
  "reason": "Complexity threshold exceeded (0.82 > 0.65)",
  "timestamp": 1734168350,
  "decision_reason": "User asked about advanced quantum entanglement theory",
  "cycle_detected": false,
  "request_preview": "Explain the mathematical foundations of quantum entanglement...",
  "response_preview": "Quantum entanglement is a phenomenon where..."
}
```

## API Reference

### Base URL
All dashboard API endpoints are prefixed with `/api/dashboard`.

### Common Response Format

```json
{
  "status": "success",
  "message": "Operation completed",
  "data": { ... }
}
```

Error responses follow the format:

```json
{
  "status": "error",
  "message": "Error description",
  "error": "Detailed error message"
}
```

### Detailed Endpoint Documentation

#### GET `/api/dashboard/live`

Returns live model state for the Live Traffic tab.

**Response:**
```json
{
  "models": [
    {
      "id": "string",
      "config": {
        "display_name": "string",
        "status": "active|inactive|disabled",
        "limits": {
          "requests_per_minute": 15,
          "requests_per_day": 1500
        },
        "pricing": {
          "usage_tiers": [
            {
              "name": "string",
              "threshold_requests": 1000,
              "input_cost": 0.5,
              "output_cost": 1.0
            }
          ]
        }
      },
      "state": {
        "current_rpm": 8.2,
        "requests_today": 342,
        "total_cost_session": 0.45,
        "last_updated_ts": "2025-12-14T10:25:45.982Z"
      }
    }
  ]
}
```

#### GET `/api/dashboard/metrics`

Returns performance metrics for charts and counters.

**Response:**
```json
{
  "total_fallbacks": 12,
  "judge_latency": {
    "avg_ms": 245.6,
    "min_ms": 120,
    "max_ms": 890
  },
  "weak_model_latency": {
    "avg_ms": 320.1,
    "min_ms": 150,
    "max_ms": 1200
  },
  "strong_model_latency": {
    "avg_ms": 450.3,
    "min_ms": 200,
    "max_ms": 1500
  },
  "latency_series": {
    "labels": ["1", "2", "3", ...],
    "judge": [120, 135, 245, ...],
    "weak": [150, 320, 280, ...],
    "strong": [200, 450, 500, ...]
  },
  "judge_success_rate": 95.2,
  "judge_skip_rate": 15.8,
  "judge_call_count": 125,
  "judge_fallback_count": 8,
  "judge_breakdown": {
    "gemini-1.5-flash": {
      "calls": 45,
      "success": 44,
      "failures": 1,
      "avg_latency": 230.5
    }
  },
  "fallback_chain": [
    {
      "timestamp": 1734168350,
      "primary_id": "gemini-1.5-flash",
      "backup_id": "gemini-1.5-pro"
    }
  ]
}
```

#### POST `/api/dashboard/model/{model_id}/reset-cost`

Reset the session cost for a specific model.

**Request Body:** None required

**Response:**
```json
{
  "status": "success",
  "message": "Cost reset for deepseek-chat"
}
```

#### GET `/api/dashboard/configuration`

Returns configuration data for the Configuration tab.

**Response:**
```json
{
  "api_keys": {
    "DEEPSEEK_API_KEY": "sk-...****",
    "ANTHROPIC_API_KEY": "sk-ant-...****",
    "GEMINI_BACKUP1_API_KEY": "AIza...****",
    "GEMINI_BACKUP2_API_KEY": "AIza...****"
  },
  "models": [
    {
      "id": "deepseek-chat",
      "config": {
        "display_name": "DeepSeek Chat",
        "routing": {
          "priority_group": "fast_tier",
          "order": 1
        },
        "limits": {
          "requests_per_minute": 15
        }
      }
    }
  ],
  "system_settings": {
    "default_tier": "free",
    "session_id_strategy": "uuid",
    "max_cost_per_session": 5.0
  }
}
```

#### GET `/api/dashboard/logs`

Retrieve recent routing decision logs.

**Query Parameters:**
- `limit` (optional): Number of logs to return (default: 50)
- `include_preview` (optional): Include request/response previews (default: false)

**Response:**
```json
{
  "logs": [
    {
      "session_id": "session_abc123",
      "request_id": "req_xyz789",
      "model_used": "claude-3-5-sonnet",
      "complexity_score": 0.82,
      "cost_incurred": 0.035,
      "impact_scope": "HIGH",
      "reason": "Complexity threshold exceeded",
      "timestamp": 1734168350,
      "decision_reason": "User asked about advanced quantum entanglement theory",
      "cycle_detected": false,
      "request_preview": "Explain the mathematical foundations...",
      "response_preview": "Quantum entanglement is a phenomenon..."
    }
  ]
}
```

## Dashboard Customization

### Custom Styling

The dashboard uses inline CSS that can be modified in `sentinelrouter/sentinelrouter/dashboard.py`. Key style sections:

1. **Color Scheme**: Defined in the `body` background gradient and `metric-card` colors
2. **Layout**: Grid and flexbox layouts in `.model-grid` and `.config-section`
3. **Responsive Design**: Media queries can be added for mobile support

### Adding New Tabs

To add a new tab to the dashboard:

1. Add the tab button in the HTML template (around line 498)
2. Create the tab content div with unique ID
3. Add JavaScript functions to load the tab data
4. Implement backend API endpoints if needed

### Extending API Endpoints

New dashboard endpoints should follow the pattern:

```python
@dashboard_app.get("/api/dashboard/new-endpoint")
async def new_endpoint():
    # Implementation
    return JSONResponse({"data": ...})
```

## Integration with Main Server

The dashboard integrates with the main server in several ways:

### Shared Database
Both servers access the same SQLite database (`sentinelrouter.db`) via SQLAlchemy models.

### Shared Configuration
Both servers read from the same `config/models_config.json` and environment variables.

### State Management
The dashboard uses the same `StateManager` instance to ensure configuration changes are reflected in routing decisions.

### Startup Integration
When the main server starts (`server.py`), it spawns the dashboard in a separate thread:

```python
# In server.py main block
dashboard_thread = threading.Thread(
    target=start_dashboard_server,
    kwargs={"host": "0.0.0.0", "port": 8001},
    daemon=True
)
dashboard_thread.start()
```

## Troubleshooting Dashboard Issues

### Common Issues and Solutions

| Issue | Possible Cause | Solution |
|-------|---------------|----------|
| Dashboard not loading | Port 8001 already in use | Change port in `server.py` or stop conflicting process |
| "Cannot GET /" | Dashboard server not running | Check if dashboard thread started successfully |
| No live data | Database connection issue | Verify `sentinelrouter.db` exists and is accessible |
| Configuration changes not saved | StateManager persistence issue | Check file permissions for `config/models_config.json` |
| CORS errors | Browser security restrictions | Configure `CORS_ORIGINS` environment variable |

### Logging

Dashboard-specific logs are prefixed with `sentinelrouter.dashboard`:

```python
import logging
logger = logging.getLogger("sentinelrouter.dashboard")
```

Log level can be controlled via the `LOG_LEVEL` environment variable.

## Security Considerations

1. **API Exposure**: The dashboard exposes internal metrics and configuration. Ensure it's not publicly accessible in production.
2. **Authentication**: Implement authentication via reverse proxy or FastAPI middleware.
3. **Data Validation**: All configuration updates should be validated against Pydantic schemas.
4. **Rate Limiting**: Consider adding rate limiting to dashboard API endpoints.
5. **HTTPS**: Always run the dashboard behind HTTPS in production.

## Example: Monitoring Script

Here's a Python script to programmatically monitor dashboard metrics:

```python
import requests
import time

class DashboardMonitor:
    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url
    
    def get_live_metrics(self):
        """Fetch live metrics for alerting."""
        response = requests.get(f"{self.base_url}/api/dashboard/metrics")
        data = response.json()
        
        # Check for anomalies
        if data["judge_success_rate"] < 80:
            print(f"WARNING: Judge success rate low: {data['judge_success_rate']}%")
        
        if data["total_fallbacks"] > 10:
            print(f"WARNING: High fallback count: {data['total_fallbacks']}")
        
        return data
    
    def reset_model_costs(self, model_id):
        """Reset a model's session cost."""
        response = requests.post(
            f"{self.base_url}/api/dashboard/model/{model_id}/reset-cost"
        )
        return response.json()

# Usage
monitor = DashboardMonitor()
while True:
    metrics = monitor.get_live_metrics()
    print(f"Requests today: {sum(m['state']['requests_today'] for m in metrics['models'])}")
    time.sleep(60)  # Check every minute
```

## Related Documentation

- [Main API Reference](rest-api.md) - Documentation for the primary chat completions API
- [Configuration Guide](../getting-started/configuration.md) - Detailed configuration options
- [Architecture Overview](../architecture/overview.md) - System architecture and components

---

**Next Steps**: 
- Explore the [Headers and Metrics](headers-and-metrics.md) documentation for custom headers returned by the API
- Learn about [Testing](../development/testing.md) the dashboard functionality
- Review [Troubleshooting](../operations/troubleshooting.md) for common dashboard issues