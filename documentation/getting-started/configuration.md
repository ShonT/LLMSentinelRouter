# Configuration Guide

SentinelRouter uses a unified configuration system that combines a JSON configuration file, environment variables, and runtime state management. This guide explains how to configure the system for development and production.

## Overview

The configuration system is designed to be:

- **Centralized**: All settings are defined in a single JSON file (`config/models_config.json`).
- **Hierarchical**: Settings are organized by system, model, judge, and routing.
- **Dynamic**: Many settings can be updated at runtime via the dashboard or API.
- **Validated**: All configuration is validated using Pydantic schemas.

## Configuration Sources

SentinelRouter loads configuration from three sources, in order of precedence:

1. **Environment Variables** – Highest priority, used for secrets and deployment‑specific overrides.
2. **`models_config.json`** – Primary configuration file defining models, limits, pricing, and routing.
3. **Session Defaults** – Default values for sessions (tier, judge usage, session‑ID strategy).

## Environment Variables

Create a `.env` file (or set environment variables) with the following:

```bash
# API Keys (required for LLM providers)
DEEPSEEK_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AIza...

# Server Settings
WORKERS=2
PORT=8000
LOG_LEVEL=INFO
PERSISTENCE_INTERVAL_SECONDS=5

# Feature Toggles
ENABLE_DASHBOARD=true
ENABLE_METRICS=true
ENABLE_SEMANTIC_CACHE=true

# Database
DATABASE_URL=sqlite:///./data/sentinelrouter.db
```

See `.env.example` for a complete list.

## Unified Configuration File

The main configuration file is `config/models_config.json`. It is structured as follows:

```json
{
  "system_settings": { ... },
  "models": { ... },
  "judge_config": { ... },
  "routing_order_config": { ... }
}
```

### System Settings

`system_settings` defines global behavior:

```json
"system_settings": {
  "persistence_interval_seconds": 5,
  "default_routing_strategy": "waterfall",
  "timezone": "UTC",
  "session_defaults": {
    "default_session_id": "default-uuid-001",
    "default_tier": "free",
    "default_use_judge": null,
    "session_id_strategy": "uuid"
  }
}
```

- **`persistence_interval_seconds`**: How often the StateManager writes dirty state to disk.
- **`default_routing_strategy`**: Either `"waterfall"` (try weak models first) or `"priority"` (use model priority groups).
- **`session_defaults`**: Default values for new sessions (see below).

### Model Configuration

Each model is defined under the `models` key. Example for DeepSeek Chat:

```json
"deepseek-chat": {
  "display_name": "DeepSeek Chat",
  "provider": "deepseek",
  "model_key": "deepseek-chat",
  "status": "ACTIVE",
  "capabilities": { ... },
  "routing": { ... },
  "limits": { ... },
  "free_tier_limits": { ... },
  "paid_tier_limits": { ... },
  "pricing": { ... },
  "cost": { ... },
  "state": { ... }
}
```

#### Key Fields

- **`display_name`**: Human‑readable name.
- **`provider`**: One of `deepseek`, `anthropic`, `gemini`, `groq`, `openrouter`.
- **`model_key`**: Provider‑specific model identifier (e.g., `"deepseek-chat"`, `"llama-3.1-8b-instant"`).
- **`status`**: `"ACTIVE"` or `"BANNED"`.
- **`capabilities`**: Supported modalities and context window.
- **`routing`**: Priority group (`fast_tier` or `strong_tier`) and order within that group.
- **`limits`**: Global rate limits (requests per minute, per day, tokens per minute).
- **`free_tier_limits` / `paid_tier_limits`**: Tier‑specific limits (used when a session’s tier matches).
- **`pricing`**: Cost per million tokens (`input_cost_per_m`, `output_cost_per_m`) and optional usage tiers.
- **`cost`**: Simple per‑call and per‑token cost (alternative to pricing tiers).
- **`state`**: Runtime state (current RPM, requests today, etc.) – managed by the system.

### Judge Configuration

`judge_config` defines the judge model(s) used for complexity assessment:

```json
"judge_config": {
  "model_order": [
    "gemini-2.5-flash-lite-primary",
    "deepseek-judge-backup1"
  ],
  "is_judge_required": false
}
```

- **`model_order`**: List of model IDs to use as judges (primary first, then backups).
- **`is_judge_required`**: If `true`, every request must be judged; if `false`, judge is used only when `use_judge` is `true` or `null` (smart mode).

### Routing Order Configuration

`routing_order_config` defines which models are considered “strong” and “weak”:

```json
"routing_order_config": {
  "strong_models": [
    "claude-opus-4"
  ],
  "weak_models": [
    "deepseek-chat"
  ]
}
```

These lists are used by the waterfall routing strategy to decide which model to try first.

## Session Configuration

Each client session can have its own configuration, which overrides the system defaults. Sessions are identified by a `session_id` (provided via the `X-Session-ID` header or auto‑generated).

### Session‑Level Settings

- **`tier`**: `"free"` or `"paid"` – determines which rate‑limit set (`free_tier_limits` vs `paid_tier_limits`) is applied.
- **`use_judge`**:
  - `true` – always use judge (complexity scoring).
  - `false` – never use judge (direct routing).
  - `null` – smart mode (judge is used only for ambiguous prompts).
- **`session_id_strategy`**: How to generate session IDs when none is provided. Options: `"uuid"`, `"ip_based"`, `"custom"`.

Session defaults are set in `system_settings.session_defaults` and can be overridden per request via headers:

- `X-Session-Tier`: `free` or `paid`
- `X-Use-Judge`: `true`, `false`, or `smart`

## Adding a New Model

To add a new LLM provider:

1. **Define the model in `models_config.json`**:

   ```json
   "my-new-model": {
     "display_name": "My New Model",
     "provider": "anthropic",  // or deepseek, gemini, groq, openrouter
     "model_key": "claude-3-5-sonnet-20241022",
     "status": "ACTIVE",
     "capabilities": {
       "modality": ["text"],
       "context_window": 200000
     },
     "routing": {
       "priority_group": "strong_tier",
       "order": 2
     },
     "limits": { ... },
     "free_tier_limits": { ... },
     "paid_tier_limits": { ... },
     "pricing": { ... },
     "cost": { ... }
   }
   ```

2. **Ensure the provider client is implemented** in `sentinelrouter/sentinelrouter/clients.py`. If not, you may need to extend the client registry.

3. **Add the model to the routing order** in `routing_order_config.strong_models` or `weak_models`.

4. **Restart the server** (or use the dashboard to reload configuration).

## Configuration Validation

The configuration is validated at startup using the Pydantic schemas in `sentinelrouter/schemas/config_models.py`. Common validation errors include:

- Missing required fields.
- Invalid enum values (e.g., `provider` not in `["deepseek","anthropic","gemini"]`).
- Negative rate limits.

If the configuration is invalid, the server will fail to start with a descriptive error.

## Runtime Configuration Updates

The StateManager allows certain configuration values to be updated at runtime:

- Model state (RPM, requests today, tokens today, cost)
- Model status (ACTIVE/BANNED)
- Rate limits (via the dashboard)

To update configuration via the dashboard:

1. Navigate to the **Configuration & Keys** tab.
2. Edit the JSON directly or use the form controls.
3. Click **Save**. Changes are written to `models_config.json` asynchronously.

## Configuration Precedence

When a setting is defined in multiple places, the following precedence applies (highest to lowest):

1. **Request‑level headers** (e.g., `X-Session-Tier`, `X-Use-Judge`)
2. **Session‑level settings** (stored in the database)
3. **Environment variables** (for API keys, server settings)
4. **`models_config.json`** (unified configuration file)
5. **System defaults** (hard‑coded in `config.py`)

## Example: Full Configuration Snippet

See the default `config/models_config.json` for a complete example with DeepSeek, Claude, and Gemini models.

## Next Steps

- For production deployment, see [Docker Deployment](docker-deployment.md).
- For architecture details, see [Model Registry](../architecture/model-registry.md) and [Judge System](../architecture/judge-system.md).
- For API usage, see [REST API](../api-reference/rest-api.md).

---

*Last updated: 2025‑12‑14*