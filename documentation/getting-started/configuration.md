# Configuration Guide

SentinelRouter uses a unified configuration system that combines a JSON configuration file, environment variables, and runtime state management. This guide explains how to configure the system for development and production.

## Overview

The configuration system is designed to be:

- **Centralized**: Runtime routing and client creation use `config/sentinel_config.json`.
- **Hierarchical**: Settings are organized by keys, key instances, models, judge, and routing.
- **Dynamic**: The runtime config reloads on file changes (hot-swap).
- **Validated**: All configuration is validated using Pydantic schemas.

## Configuration Sources

SentinelRouter loads configuration from three sources, in order of precedence:

1. **`sentinel_config.json`** – Primary runtime config for keys, routing, and model definitions.
2. **Environment Variables** – Used for secrets and deployment‑specific overrides (via `${ENV}` placeholders).
3. **`models_config.json`** – Legacy config used during migration and for persisted runtime state.

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

## Runtime Configuration (`sentinel_config.json`)

The primary runtime configuration file is `config/sentinel_config.json`:

Set `SENTINEL_CONFIG_PATH` to override the default location.

```json
{
  "keys": { ... },
  "key_instances": { ... },
  "models": { ... },
  "routing_policy": { ... },
  "judge": { ... },
  "semantic_cache": { ... }
}
```

### Keys & Key Instances

Keys are stored once and referenced by key instances. Key instances include priorities for failover:

```json
"keys": {
  "deepseek_key_1": { "type": "deepseek", "value": "${DEEPSEEK_API_KEY}" }
},
"key_instances": {
  "deepseek_primary": { "key_ref": "deepseek_key_1", "priority": 0 }
}
```

### Models

Each model references one or more key instances:

```json
"deepseek-chat": {
  "enabled": true,
  "provider": "deepseek",
  "model_id": "deepseek-chat",
  "key_instances": ["deepseek_primary"],
  "pricing": { "input_cost_per_m": 0.14, "output_cost_per_m": 0.28 },
  "limits": { "requests_per_minute": 60, "requests_per_day": 10000, "tokens_per_minute": 1000000 }
}
```

#### Key Fields

- **`provider`**: Provider type (`deepseek`, `anthropic`, `gemini`, `groq`, `openrouter`).
- **`model_id`**: Provider model identifier (e.g., `deepseek-chat`).
- **`key_instances`**: Ordered list of key instances for priority and failover.
- **`pricing`**: Input/output cost per million tokens.
- **`limits`**: Requests per minute/day and tokens per minute.

### Routing Policy

`routing_policy` defines weak and strong tiers for the router:

```json
"routing_policy": {
  "weak_tier": { "order": ["deepseek-chat"] },
  "strong_tier": { "order": ["claude-3-opus"] }
}
```

## Legacy Configuration (`models_config.json`)

During migration, `config/models_config.json` continues to work:

- If `sentinel_config.json` is present, it is used for routing and client creation.
- If `sentinel_config.json` is missing, SentinelRouter derives runtime config from `models_config.json`.
- Keys are sourced from environment variables in legacy mode (single key instance per provider).

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

To add a new model in `sentinel_config.json`:

1. **Add the key (or reuse an existing key)**:

   ```json
   "keys": {
     "anthropic_key_1": {
       "type": "anthropic",
       "value": "${ANTHROPIC_API_KEY}"
     }
   }
   ```

2. **Add a key instance**:

   ```json
   "key_instances": {
     "anthropic_primary": {
       "key_ref": "anthropic_key_1",
       "priority": 0
     }
   }
   ```

3. **Define the model and add it to a routing tier**:

   ```json
   "models": {
     "claude-3-5-sonnet": {
       "enabled": true,
       "provider": "anthropic",
       "model_id": "claude-3-5-sonnet-20241022",
       "key_instances": ["anthropic_primary"],
       "pricing": { "input_cost_per_m": 3.0, "output_cost_per_m": 15.0 },
       "limits": { "requests_per_minute": 60, "requests_per_day": 10000, "tokens_per_minute": 120000 }
     }
   },
   "routing_policy": {
     "strong_tier": { "order": ["claude-3-5-sonnet"] }
   }
   ```

4. **Ensure the provider client is implemented** in `sentinelrouter/sentinelrouter/clients.py`.

5. **Save the file** – the router reloads it automatically.

## Configuration Validation

The runtime configuration is validated at startup using the Pydantic schema in `sentinelrouter/schemas/sentinel_config.py`. Common validation errors include:

- Missing required fields.
- Invalid enum values (e.g., `provider` not in the supported provider list).
- Negative rate limits.

If the configuration is invalid, the server will fail to start with a descriptive error.

## Runtime Configuration Updates

SentinelRouter reloads `sentinel_config.json` on change for routing and client creation. This enables key rotation and model changes without a restart.

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
4. **`sentinel_config.json`** (runtime configuration file)
5. **`models_config.json`** (legacy config and runtime state)
6. **System defaults** (hard‑coded in `config.py`)

## Example: Full Configuration Snippet

See `config/sentinel_config_demo.json` for a complete example with keys, key instances, and routing tiers.

## Next Steps

- For production deployment, see [Docker Deployment](docker-deployment.md).
- For architecture details, see [Model Registry](../architecture/model-registry.md) and [Judge System](../architecture/judge-system.md).
- For API usage, see [REST API](../api-reference/rest-api.md).

---

*Last updated: 2025‑12‑14*
