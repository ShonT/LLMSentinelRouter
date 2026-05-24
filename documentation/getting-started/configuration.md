# Configuration

Runtime configuration comes from environment variables and `config/sentinel_config.json`.

## Environment

Important variables:

- `HOST`, `PORT`, `DASHBOARD_PORT`
- `DATABASE_URL`
- `SENTINEL_CONFIG_PATH`
- `MODELS_CONFIG_PATH`
- `ADMIN_API_TOKEN`
- `MAX_COST_PER_SESSION`
- `INITIAL_THRESHOLD`
- `TARGET_ESCALATION_RATE`
- `CONDITIONAL_JUDGE_TIMEOUT_SECONDS`
- `ENABLE_BUDGET_KILLSWITCH`
- `ENABLE_CYCLE_DETECTION`
- `ENABLE_DYNAMIC_THRESHOLD`
- `SEMANTIC_CACHE_ENABLED`
- `REDACTION_MODE`

Provider keys:

- `DEEPSEEK_API_KEY`
- `ANTHROPIC_API_KEY`
- `GEMINI_BACKUP1_API_KEY`
- `GEMINI_BACKUP2_API_KEY`
- `GROQ_API_KEY`
- `OPENROUTER_API_KEY`

Provider base URLs can be overridden for tests with `DEEPSEEK_BASE_URL`, `ANTHROPIC_BASE_URL`, `GEMINI_BASE_URL`, `GROQ_BASE_URL`, and `OPENROUTER_BASE_URL`.

## Sentinel Config

`config/sentinel_config.json` defines:

- `keys`: provider API keys or `${ENV_NAME}` placeholders
- `key_instances`: prioritized key references
- `models`: provider, model ID, pricing, limits, and key instances
- `routing_policy`: weak and strong tier order
- `judge`: judge enablement, model order, and threshold
- `semantic_cache`: route cache enablement and thresholds

The Go loader validates references, provider/key compatibility, routing tier overlap, and judge model references at startup and on dashboard mutations.

