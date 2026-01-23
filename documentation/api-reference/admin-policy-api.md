# Admin Policy API Quick Reference

## Overview
The Admin Policy API provides operator-grade controls for runtime policy tuning without requiring server restarts or exposing sensitive configuration.

## Base URL
```
http://localhost:8000
```

## Endpoints

### 1. Get Current Policy
```http
GET /api/admin/policy
```

**Response:**
- `success`: Boolean indicating success
- `data`: Current policy configuration
  - `budget_control`: Budget and escalation settings
  - `judge`: Judge system settings
  - `semantic_cache`: Semantic cache settings
  - `cycle_detection`: Cycle detection settings
- `impact_notes`: Categorized impact warnings

**Example:**
```bash
curl http://localhost:8000/api/admin/policy | jq
```

---

### 2. Update Policy
```http
POST /api/admin/policy
Content-Type: application/json
```

**Request Body:** (all fields optional)
```json
{
  "budget_control": {
    "max_cost_per_session": 30.0,
    "escalation_rate_limit": 0.08,
    "rolling_window_size": 25
  },
  "judge": {
    "enabled": true,
    "mode": "smart",
    "complexity_threshold": 0.6
  },
  "semantic_cache": {
    "enabled": true,
    "min_samples": 3,
    "confidence_threshold": 0.75,
    "ttl_seconds": 604800
  },
  "cycle_detection": {
    "enabled": true,
    "window_size": 100,
    "simhash_distance_threshold": 3
  }
}
```

**Response:**
- `success`: Boolean
- `message`: Status message
- `warnings`: Array of warning messages for changes affecting sessions
- `data`: Updated policy fields

**Example:**
```bash
curl -X POST http://localhost:8000/api/admin/policy \
  -H "Content-Type: application/json" \
  -d '{"judge": {"complexity_threshold": 0.7}}'
```

---

### 3. Get System State (Read-Only)
```http
GET /api/admin/state
```

**Response:**
- `success`: Boolean
- `data`: Read-only state information
  - `routing`: Model tiers and routing configuration
  - `judge`: Judge effectiveness metrics
  - `semantic_cache`: Cache performance metrics
  - `escalation`: Escalation behavior metrics
- `note`: Reminder about read-only nature

**Example:**
```bash
curl http://localhost:8000/api/admin/state | jq
```

---

### 4. Reset Semantic Cache
```http
POST /api/admin/reset-cache
```

**Use Case:** After changing `min_samples` or `ttl_seconds`

**Response:**
```json
{
  "success": true,
  "message": "Semantic cache reset successfully"
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/api/admin/reset-cache
```

---

### 5. Reset Escalation Counters
```http
POST /api/admin/reset-escalation
```

**Use Case:** After changing `rolling_window_size` or `escalation_rate_limit`

**Response:**
```json
{
  "success": true,
  "message": "Escalation counters reset successfully"
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/api/admin/reset-escalation
```

---

## Policy Fields Reference

### Budget Control
| Field | Type | Default | Range | Impact |
|-------|------|---------|-------|--------|
| `max_cost_per_session` | float | 25.0 | ≥ 0.0 | ⚠️ Warning: May block in-flight sessions |
| `escalation_rate_limit` | float | 0.05 | 0.0 - 1.0 | Immediate |
| `rolling_window_size` | int | 20 | ≥ 1 | Soft reset recommended |

### Judge Policy
| Field | Type | Default | Options | Impact |
|-------|------|---------|---------|--------|
| `enabled` | bool | false | true/false | Immediate |
| `mode` | string | "smart" | "always", "never", "smart" | Immediate |
| `complexity_threshold` | float | 0.5 | 0.0 - 1.0 | Immediate |

### Semantic Cache Policy
| Field | Type | Default | Range | Impact |
|-------|------|---------|-------|--------|
| `enabled` | bool | false | true/false | Immediate |
| `min_samples` | int | 3 | ≥ 1 | Soft reset recommended |
| `confidence_threshold` | float | 0.75 | 0.0 - 1.0 | Immediate |
| `ttl_seconds` | int | 604800 | ≥ 0 | Soft reset recommended |

### Cycle Detection Policy
| Field | Type | Default | Range | Impact |
|-------|------|---------|-------|--------|
| `enabled` | bool | true | true/false | Immediate |
| `window_size` | int | 100 | ≥ 1 | Immediate |
| `simhash_distance_threshold` | int | 3 | ≥ 0 | Immediate |

---

## Impact Categories

### Immediate Effect
Changes take effect immediately without any additional action required:
- `judge.enabled`
- `judge.mode`
- `complexity_threshold`
- `escalation_rate_limit`
- `cycle_detection.enabled`

### Soft Reset Recommended
Changes take effect, but resetting associated state is recommended:
- `semantic_cache.min_samples` → Reset cache
- `semantic_cache.ttl_seconds` → Reset cache
- `rolling_window_size` → Reset escalation counters

### Warning Required
Changes may immediately affect in-flight sessions:
- `max_cost_per_session` → May block sessions exceeding new limit

---

## Safety Guarantees

✅ **Cannot modify:**
- API keys or credentials
- Model definitions
- Routing topology (weak/strong tiers)
- Provider configurations

✅ **Can only modify:**
- Policy thresholds and limits
- Feature enable/disable flags
- Learning system parameters

✅ **All changes:**
- Apply without server restart
- Are validated before acceptance
- Include clear impact warnings

---

## Common Workflows

### Adjust Judge Sensitivity
```bash
# Make judge more selective (higher threshold = fewer escalations)
curl -X POST http://localhost:8000/api/admin/policy \
  -H "Content-Type: application/json" \
  -d '{"judge": {"complexity_threshold": 0.7}}'
```

### Increase Session Budget
```bash
# Increase budget limit for paid tier sessions
curl -X POST http://localhost:8000/api/admin/policy \
  -H "Content-Type: application/json" \
  -d '{"budget_control": {"max_cost_per_session": 50.0}}'
```

### Tune Escalation Rate
```bash
# Allow higher escalation rate (more strong model usage)
curl -X POST http://localhost:8000/api/admin/policy \
  -H "Content-Type: application/json" \
  -d '{"budget_control": {"escalation_rate_limit": 0.10}}'

# Then reset counters to apply immediately
curl -X POST http://localhost:8000/api/admin/reset-escalation
```

### Adjust Semantic Cache
```bash
# Require more samples before trusting cache
curl -X POST http://localhost:8000/api/admin/policy \
  -H "Content-Type: application/json" \
  -d '{"semantic_cache": {"min_samples": 5, "confidence_threshold": 0.85}}'

# Reset cache to apply new thresholds
curl -X POST http://localhost:8000/api/admin/reset-cache
```

---

## Error Handling

All endpoints return consistent error responses:

```json
{
  "success": false,
  "error": "Error message describing what went wrong"
}
```

Common HTTP status codes:
- `200`: Success
- `400`: Invalid request (validation error)
- `500`: Server error

---

## Monitoring Recommendations

1. **Track policy changes** via audit logs
2. **Monitor escalation rate** after adjusting thresholds
3. **Watch session costs** after budget changes
4. **Observe cache hit rates** after semantic cache tuning
5. **Check judge effectiveness** via `/api/admin/state` metrics

---

## Related Documentation

- [Admin UI Implementation](../internal/ADMIN_UI_IMPLEMENTATION.md)
- [Configuration Guide](../getting-started/configuration.md)
- [Dashboard API Reference](../api-reference/dashboard-api.md)
