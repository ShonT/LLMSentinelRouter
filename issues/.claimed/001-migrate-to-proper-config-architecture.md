# Migrate to Proper Config Architecture with Key Rotation Support

## Problem

Your current system uses models_config.json with direct environment variable-to-client mappings, which creates a tight coupling between API keys and model configurations. This architecture has significant limitations:

1. **No key rotation support** - If you want to use multiple API keys for the same provider (e.g., two Groq keys for load balancing or quota management), you can't do it without code changes

2. **No key instance abstraction** - Every provider has exactly one hardcoded key path (GROQ_API_KEY, GEMINI_BACKUP2_API_KEY), making it impossible to A/B test keys, implement failover between different API accounts, or segregate usage by team/project

3. **Security and maintenance issues** - Currently, if one API key hits rate limits or expires, you must manually edit .env, restart Docker, and hope no requests fail during the transition

## Solution

The demo config in sentinel_config_demo.json demonstrates a proper three-layer architecture (Keys → Key Instances → Models) that enables key rotation, multi-tenant deployments, and dynamic key switching without restarting the server. 

The Pydantic-based sentinel_config_demo.json approach solves this by:
- Decoupling key management from model configuration
- Allowing hot-swapping of keys
- Priority-based key selection
- Proper separation of concerns between secrets management and routing logic

## Impact

**Bottom line**: You can't scale beyond single-key-per-provider without migrating to the proper config architecture.

## Acceptance Criteria

- [ ] Implement three-layer architecture (Keys → Key Instances → Models)
- [ ] Support multiple API keys per provider
- [ ] Enable key rotation without service restart
- [ ] Implement priority-based key selection
- [ ] Add failover support between different API accounts
- [ ] Maintain backward compatibility during migration
- [ ] Update documentation with new configuration approach
