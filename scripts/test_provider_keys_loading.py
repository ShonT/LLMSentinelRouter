#!/usr/bin/env python3
"""
Test script to verify all provider API keys are loaded correctly from .env file.
This ensures the legacy config format properly reads keys via Settings.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sentinelrouter.sentinelrouter.config import get_runtime_config_with_meta


def test_provider_keys():
    """Test that all provider keys are loaded from .env."""
    print("=" * 70)
    print("PROVIDER API KEY LOADING TEST")
    print("=" * 70)

    runtime_config, _ = get_runtime_config_with_meta()

    # Expected providers in .env
    expected_providers = {
        "deepseek": "DEEPSEEK_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "gemini": "GEMINI_BACKUP1_API_KEY",
        "groq": "GROQ_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }

    print(f"\nTotal keys in config: {len(runtime_config.keys)}")
    print(f"Total key_instances in config: {len(runtime_config.key_instances)}\n")

    results = {}
    for provider, env_var in expected_providers.items():
        # Find keys for this provider
        provider_keys = {
            k: v for k, v in runtime_config.keys.items() if provider in k.lower()
        }

        if not provider_keys:
            results[provider] = {"status": "❌ MISSING", "detail": "No key found"}
            continue

        # Check if key has a value
        key_id = list(provider_keys.keys())[0]
        key_obj = provider_keys[key_id]
        
        if not key_obj.value or key_obj.value == "":
            results[provider] = {
                "status": "❌ EMPTY",
                "detail": f"Key exists but value is empty",
            }
        else:
            value_preview = key_obj.value[:15] + "..."
            results[provider] = {
                "status": "✅ LOADED",
                "detail": f"Key: {key_id}, Value: {value_preview}",
            }

    # Print results
    print("Provider Key Loading Results:")
    print("-" * 70)
    for provider in expected_providers.keys():
        result = results.get(provider, {"status": "❌ UNKNOWN", "detail": "Not tested"})
        print(f"{provider.upper():15} {result['status']:12} {result['detail']}")

    # Check key instances are properly linked
    print("\n" + "=" * 70)
    print("KEY INSTANCE VALIDATION")
    print("=" * 70)

    for instance_id, instance in runtime_config.key_instances.items():
        key = runtime_config.keys.get(instance.key_ref)
        if not key:
            print(f"❌ {instance_id}: References missing key '{instance.key_ref}'")
        elif not key.value:
            print(f"⚠️  {instance_id}: Key '{instance.key_ref}' has no value")
        else:
            print(f"✅ {instance_id}: Linked to {key.type}, enabled={instance.enabled}")

    # Summary
    print("\n" + "=" * 70)
    loaded_count = sum(1 for r in results.values() if "✅" in r["status"])
    total_count = len(expected_providers)
    print(f"SUMMARY: {loaded_count}/{total_count} providers have valid keys")
    
    if loaded_count == total_count:
        print("✅ ALL PROVIDER KEYS LOADED SUCCESSFULLY")
        return 0
    else:
        print("❌ SOME PROVIDERS MISSING OR EMPTY KEYS")
        print("\nNote: Optional providers (Groq, OpenRouter) may not have keys configured.")
        print("Required providers (DeepSeek, Anthropic, Gemini) must have keys.")
        return 1


if __name__ == "__main__":
    exit_code = test_provider_keys()
    sys.exit(exit_code)
