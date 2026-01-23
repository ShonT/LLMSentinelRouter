# Quick Reference: Pydantic Configuration

## Validate Configuration

```bash
python scripts/validate_config.py config/your_config.json
```

## Run Tests

```bash
python scripts/test_sentinel_config.py
```

## Configuration Structure

```json
{
  "keys": {
    "key_id": {"type": "groq|deepseek|anthropic|gemini|openrouter", "value": "API_KEY"}
  },
  "key_instances": {
    "instance_name": {"key_ref": "key_id", "description": "Optional"}
  },
  "models": {
    "model_name": {
      "enabled": true,
      "provider": "groq",
      "model_id": "provider_model_id",
      "key_instance": "instance_name",
      "display_name": "Display Name",
      "pricing": {"input_cost_per_m": 0.0, "output_cost_per_m": 0.0},
      "limits": {
        "requests_per_minute": 0,
        "requests_per_day": 0,
        "tokens_per_minute": 0
      }
    }
  },
  "routing_policy": {
    "weak_tier": {"order": ["model1", "model2"]},
    "strong_tier": {"order": ["model3"]}
  },
  "judge": {
    "enabled": false,
    "model_order": [],
    "complexity_threshold": 0.5
  },
  "semantic_cache": {
    "enabled": false,
    "min_samples": 3,
    "confidence_threshold": 0.75,
    "ttl_seconds": 604800
  }
}
```

## Validation Rules

| Rule | Requirement |
|------|-------------|
| Keys | All key_instances must reference existing keys |
| Models | All models must reference existing key_instances |
| Provider Match | Model provider must match key provider type |
| Tier Models | Must exist and be enabled |
| Tier Overlap | Models cannot be in both weak and strong tiers |
| Empty Tiers | Both weak and strong tiers must have at least one model |
| Judge | If enabled, model_order must not be empty |
| Judge Models | Must exist and be enabled |

## Common Errors

### KeyInstance refers to missing key
**Fix:** Add the key to `keys` or update `key_ref`

### Model provider doesn't match key provider
**Fix:** Use a key instance with matching provider type

### Models cannot appear in both tiers
**Fix:** Remove model from either weak_tier or strong_tier

### Tier is empty
**Fix:** Add at least one enabled model to the tier

### Judge enabled but model_order is empty
**Fix:** Add models to judge.model_order or set enabled=false

## Files

- **Schema:** `sentinelrouter/schemas/sentinel_config.py`
- **Demo:** `config/sentinel_config_demo.json`
- **Tests:** `scripts/test_sentinel_config.py`
- **Validator:** `scripts/validate_config.py`
- **Docs:** `documentation/configuration/pydantic-config.md`
