# SentinelRouter Pydantic Configuration System

## Overview

The new Pydantic-based configuration system provides **operator-grade validation** with:

- ✅ **Referential Integrity**: All references between keys, key instances, and models are validated at load time
- ✅ **Type Safety**: Provider types must match between keys and models  
- ✅ **Policy Validation**: Routing tiers cannot be empty, overlap, or reference disabled/missing models
- ✅ **Judge System Validation**: Judge configuration is validated against available models
- ✅ **Clear Error Messages**: Every validation error explains exactly what needs to be fixed
- ✅ **Intentional Flexibility**: Supports advanced use cases like semantic cache without judge (with warnings)

## Configuration Structure

### Keys

API credentials for each provider:

```json
{
  "keys": {
    "groq_key_1": {
      "type": "groq",
      "value": "${GROQ_API_KEY}"
    }
  }
}
```

### Key Instances

Named references to keys, allowing multiple instances per provider with priority:

```json
{
  "key_instances": {
    "groq_primary": {
      "key_ref": "groq_key_1",
      "priority": 0,
      "description": "Primary Groq API key for fast inference"
    },
    "groq_backup": {
      "key_ref": "groq_key_2",
      "priority": 1,
      "description": "Backup Groq key for failover"
    }
  }
}
```

### Models

Model definitions with pricing and limits:

```json
{
  "models": {
    "groq-llama-3.1-8b": {
      "enabled": true,
      "provider": "groq",
      "model_id": "llama-3.1-8b-instant",
      "key_instances": ["groq_primary", "groq_backup"],
      "display_name": "Llama 3.1 8B Instant (Groq)",
      "pricing": {
        "input_cost_per_m": 0.05,
        "output_cost_per_m": 0.08
      },
      "limits": {
        "requests_per_minute": 30,
        "requests_per_day": 14400,
        "tokens_per_minute": 30000
      }
    }
  }
}
```

**Important**: The `enabled` field allows you to disable models without deleting their configuration. Disabled models cannot be used in routing or judge configurations.
**Failover**: `key_instances` are tried in priority order. If a key instance fails, the router tries the next key instance before falling back to another model.

### Routing Policy

Defines weak (fast/cheap) and strong (slow/expensive) tiers:

```json
{
  "routing_policy": {
    "weak_tier": {
      "order": ["groq-llama-3.1-8b", "deepseek-chat"]
    },
    "strong_tier": {
      "order": ["claude-3-opus"]
    }
  }
}
```

**Validation Rules:**
- ❌ Tiers cannot be empty
- ❌ Models cannot appear in both tiers
- ❌ Tiers cannot reference disabled or missing models

### Judge Configuration

```json
{
  "judge": {
    "enabled": true,
    "model_order": ["gemini-flash", "deepseek-chat"],
    "complexity_threshold": 0.5
  }
}
```

**Validation Rules:**
- ❌ If `enabled` is true, `model_order` cannot be empty
- ❌ All models in `model_order` must exist and be enabled

### Semantic Cache Configuration

```json
{
  "semantic_cache": {
    "enabled": true,
    "min_samples": 3,
    "confidence_threshold": 0.75,
    "ttl_seconds": 604800
  }
}
```

**Note**: Enabling semantic cache without judge will produce a warning but is allowed (useful for systems with historical data).

## Validation at Load Time

All validation happens when the configuration is loaded:

```python
from sentinelrouter.schemas.sentinel_config import SentinelConfig
import json

# Load and validate
with open("config.json") as f:
    config_dict = json.load(f)

try:
    config = SentinelConfig(**config_dict)
    print("✅ Configuration is valid!")
except ValueError as e:
    print(f"❌ Configuration error: {e}")
```

## Runtime Reload & Key Rotation

SentinelRouter reloads `sentinel_config.json` when the file changes. This enables:

- **Key rotation without restart**: Update the key value in `keys` and save the file.
- **Priority-based failover**: Multiple `key_instances` are tried in order until one succeeds.

## Legacy Compatibility

During migration, `config/models_config.json` continues to work:

- If `sentinel_config.json` is present, it is the primary source of routing and client creation.
- If `sentinel_config.json` is missing, SentinelRouter builds a runtime config from `models_config.json` and environment variables.
- Legacy configs use a single key instance per provider and rely on environment variables for key values.

## Complete Validation Checklist

### ✅ Key Management
- [x] All `key_instances` reference existing `keys`
- [x] Key types match provider types
- [x] Key instances can be prioritized and disabled

### ✅ Model Configuration  
- [x] All models reference existing `key_instances`
- [x] Enabled models have at least one enabled key instance
- [x] Model provider matches key provider type
- [x] All pricing and limits are specified
- [x] Disabled models have `enabled: false`

### ✅ Routing Policy
- [x] Weak tier is not empty
- [x] Strong tier is not empty
- [x] No model appears in both tiers
- [x] All tier models exist and are enabled

### ✅ Judge System
- [x] If enabled, `model_order` is not empty
- [x] All judge models exist and are enabled

### ✅ Semantic Cache
- [x] Warning if enabled without judge

## Demo Configuration

A complete working configuration is available at:
```
config/sentinel_config_demo.json
```

## Testing

Run the comprehensive test suite:

```bash
python scripts/test_sentinel_config.py
```

This tests:
- ✅ Valid minimal configuration
- ✅ Valid demo configuration from file
- ✅ Valid configuration with disabled model
- ❌ Missing key reference
- ❌ Missing key instance reference
- ❌ Provider type mismatch
- ❌ Empty routing tier
- ❌ Tier referencing missing model
- ❌ Tier referencing disabled model
- ❌ Model in both tiers
- ❌ Judge enabled with empty model order
- ❌ Judge referencing missing model
- ⚠️ Semantic cache enabled without judge

## Migration from Old Config

The old `models_config.json` format is still supported for backward compatibility, but new deployments should use the new Pydantic schema for:

1. **Better Validation**: Catch errors at load time, not runtime
2. **Type Safety**: Pydantic ensures all fields have correct types
3. **Clear Errors**: Know exactly what's wrong and where
4. **Documentation**: Schema is self-documenting via field descriptions

## Environment Variable Support

Keys support environment variable substitution:

```json
{
  "keys": {
    "groq_key_1": {
      "type": "groq",
      "value": "${GROQ_API_KEY}"
    }
  }
}
```

Make sure to set these in your `.env` file or environment.

## Advanced Use Cases

### Multiple Keys Per Provider

```json
{
  "keys": {
    "groq_primary": {"type": "groq", "value": "${GROQ_PRIMARY}"},
    "groq_backup": {"type": "groq", "value": "${GROQ_BACKUP}"}
  },
  "key_instances": {
    "groq_fast": {"key_ref": "groq_primary"},
    "groq_reliable": {"key_ref": "groq_backup"}
  }
}
```

### Disabling Models for Maintenance

```json
{
  "models": {
    "my-model": {
      "enabled": false,
      ...
    }
  }
}
```

The model stays in config but won't be used in routing or judging.

### Semantic Cache Without Judge

```json
{
  "judge": {"enabled": false},
  "semantic_cache": {"enabled": true}
}
```

This produces a warning but is allowed. Useful when you have historical routing data but don't want active judging.

## Error Examples

### ❌ Missing Key Reference

```
ValueError: KeyInstance 'groq_primary' refers to missing key 'nonexistent_key'
```

**Fix**: Add the key to the `keys` section or update the `key_ref`.

### ❌ Provider Mismatch

```
ValueError: Model 'my-model' provider 'anthropic' does not match key 'key1' provider 'groq'
```

**Fix**: Use a key instance that matches the model's provider type.

### ❌ Tier Overlap

```
ValueError: Models cannot appear in both weak and strong tiers: ['model1']
```

**Fix**: Remove the model from one of the tiers.

### ❌ Empty Tier

```
ValueError: routing_policy.weak_tier.order must not be empty
```

**Fix**: Add at least one enabled model to the tier.

## Schema Reference

See [`sentinelrouter/schemas/sentinel_config.py`](../sentinelrouter/schemas/sentinel_config.py) for the complete schema definition with inline documentation.
