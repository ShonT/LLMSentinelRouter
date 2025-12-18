#!/usr/bin/env python3
"""
Quick test script for Groq models integration.
Tests all three Groq models to verify they work correctly.
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sentinelrouter.sentinelrouter.clients import get_groq_client, LLMClientError


async def test_groq_model(model_key: str, model_name: str):
    """Test a single Groq model."""
    print(f"\n{'=' * 60}")
    print(f"Testing: {model_name}")
    print(f"Model Key: {model_key}")
    print(f"{'=' * 60}")
    
    try:
        client = await get_groq_client(model_key)
        
        if not client.is_available():
            print(f"❌ FAILED: Groq API key not configured (GROQ_API_KEY)")
            return False
        
        # Test simple completion
        messages = [
            {"role": "user", "content": "Say 'Hello from Groq!' and nothing else."}
        ]
        
        print("Sending test request...")
        response = await client.chat_completion(messages, temperature=0.7)
        
        print(f"✅ SUCCESS")
        print(f"Response: {response.content}")
        print(f"Model: {response.model}")
        print(f"Usage: {response.usage}")
        print(f"Cost: ${response.cost:.6f} (should be 0.0 for quota-based)")
        
        # Verify cost is zero
        assert response.cost == 0.0, f"Expected cost 0.0, got {response.cost}"
        
        return True
        
    except LLMClientError as e:
        print(f"❌ FAILED: {e}")
        return False
    except Exception as e:
        print(f"❌ FAILED (unexpected): {type(e).__name__}: {e}")
        return False


async def main():
    """Test all Groq models."""
    print("\n" + "=" * 60)
    print("GROQ MODELS INTEGRATION TEST")
    print("=" * 60)
    
    models = [
        ("llama-3.1-8b-instant", "Llama 3.1 8B Instant (Primary weak model)"),
        ("llama-3.3-70b-versatile", "Llama 3.3 70B Versatile (Better reasoning)"),
        ("qwen/qwen3-32b", "Qwen 3 32B (Fallback)"),
    ]
    
    results = {}
    
    for model_key, model_name in models:
        success = await test_groq_model(model_key, model_name)
        results[model_key] = success
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for model_key, model_name in models:
        status = "✅ PASS" if results[model_key] else "❌ FAIL"
        print(f"{status} - {model_name}")
    
    total = len(results)
    passed = sum(results.values())
    
    print(f"\nTotal: {passed}/{total} passed")
    
    if passed == total:
        print("\n🎉 All Groq models working correctly!")
        return 0
    else:
        print("\n⚠️  Some Groq models failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
