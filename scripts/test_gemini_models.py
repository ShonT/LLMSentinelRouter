#!/usr/bin/env python3
"""
Test script for Gemini models to verify API connectivity and functionality.
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sentinelrouter.sentinelrouter.clients import (
    get_gemini_backup1_client,
    get_gemini_backup2_client,
    get_gemini_flash_latest_client,
    GeminiClient,
    LLMClientError,
)
from sentinelrouter.sentinelrouter.config import get_settings


async def test_gemini_model(client_getter, model_name: str):
    """Test a single Gemini model."""
    print(f"\n{'=' * 60}")
    print(f"Testing: {model_name}")
    print(f"{'=' * 60}")
    
    try:
        client = await client_getter()
        
        # Test simple completion
        messages = [
            {"role": "user", "content": "Say 'Hello from Gemini!' and nothing else."}
        ]
        
        print("Sending test request...")
        response = await client.chat_completion(messages, temperature=0.7)
        
        print(f"✅ SUCCESS")
        print(f"Response: {response.content[:200]}...")  # First 200 chars
        print(f"Model: {response.model}")
        print(f"Usage: {response.usage}")
        print(f"Cost: ${response.cost:.6f}")
        
        return True
        
    except LLMClientError as e:
        print(f"❌ FAILED: {e}")
        return False
    except Exception as e:
        print(f"❌ FAILED (unexpected): {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Test all Gemini models."""
    print("\n" + "=" * 60)
    print("GEMINI MODELS INTEGRATION TEST")
    print("=" * 60)
    
    # Use settings to obtain available Gemini API keys. We will create lightweight
    # GeminiClient instances for the exact model IDs the user requested.
    settings = get_settings()

    def make_getter(model_id: str, api_key: str):
        async def _getter():
            return GeminiClient(api_key=api_key, model_id=model_id)
        return _getter

    models = [
        # The canonical model IDs to add to `models_config.json` are:
        #  - "gemini-2.5-flash"
        #  - "gemini-2.5-flash-lite"
        #  - "gemini-3-flash"
        (make_getter("gemini-2.5-flash", settings.gemini_backup2_api_key), "gemini-2.5-flash"),
        (make_getter("gemini-2.5-flash-lite", settings.gemini_backup2_api_key), "gemini-2.5-flash-lite"),
        (make_getter("gemini-3-flash-preview", settings.gemini_backup2_api_key), "gemini-3-flash-preview"),
    ]
    
    results = {}
    
    for client_getter, model_name in models:
        success = await test_gemini_model(client_getter, model_name)
        results[model_name] = success
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for _, model_name in models:
        status = "✅ PASS" if results[model_name] else "❌ FAIL"
        print(f"{status} - {model_name}")
    
    total = len(results)
    passed = sum(results.values())
    
    print(f"\nTotal: {passed}/{total} passed")
    
    if passed == total:
        print("\n🎉 All Gemini models working correctly!")
        return 0
    else:
        print("\n⚠️  Some Gemini models failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
