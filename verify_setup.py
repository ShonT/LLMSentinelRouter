#!/usr/bin/env python3
"""
Verification script for SentinelRouter with real API keys.
Tests that the router can successfully call DeepSeek and Anthropic APIs.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from sentinelrouter.sentinelrouter.clients import get_deepseek_client, get_anthropic_client
from sentinelrouter.sentinelrouter.config import get_settings

settings = get_settings()

async def test_deepseek():
    """Test DeepSeek API connection."""
    print(f"🔍 Testing DeepSeek API ({settings.weak_model_id})...")
    
    try:
        client = await get_deepseek_client()
        messages = [{"role": "user", "content": "Say 'Hello from DeepSeek' and nothing else."}]
        
        response = await client.chat_completion(messages)
        
        print(f"✅ DeepSeek Response:")
        print(f"   Model: {response.model}")
        print(f"   Content: {response.content[:100]}...")
        print(f"   Cost: ${response.cost:.6f}")
        print(f"   Tokens: {response.usage.get('total_tokens', 'N/A')}")
        return True
    except Exception as e:
        print(f"❌ DeepSeek Error: {str(e)}")
        return False

async def test_anthropic():
    """Test Anthropic API connection."""
    print(f"\n🔍 Testing Anthropic API ({settings.strong_model_id})...")
    
    try:
        client = await get_anthropic_client()
        messages = [{"role": "user", "content": "Say 'Hello from Anthropic' and nothing else."}]
        
        response = await client.chat_completion(messages)
        
        print(f"✅ Anthropic Response:")
        print(f"   Model: {response.model}")
        print(f"   Content: {response.content[:100]}...")
        print(f"   Cost: ${response.cost:.6f}")
        print(f"   Tokens: {response.usage.get('total_tokens', 'N/A')}")
        return True
    except Exception as e:
        print(f"❌ Anthropic Error: {str(e)}")
        return False

async def test_router_simple():
    """Test router with a simple query."""
    print("\n🔍 Testing Router with simple query...")
    
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sentinelrouter.sentinelrouter.router_logic import Router
    from sentinelrouter.sentinelrouter.database import Base
    
    # Create test database
    engine = create_engine("sqlite:///./test_verification.db")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        router = Router(db)
        
        result = await router.route(
            session_id="verification_test",
            prompt="What is 2 + 2? Answer with just the number.",
            messages=[{"role": "user", "content": "What is 2 + 2? Answer with just the number."}]
        )
        
        print(f"✅ Router Response:")
        print(f"   Model Used: {result['model_used']}")
        print(f"   Response: {result['response'].content[:100]}...")
        print(f"   Complexity Score: {result['complexity_score']:.3f}")
        print(f"   Cost: ${result['cost']:.6f}")
        print(f"   Session Cost: ${result['session_cost']:.6f}")
        print(f"   Cycle Detected: {result['cycle_detected']}")
        
        return True
    except Exception as e:
        print(f"❌ Router Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()
        # Cleanup test db
        if os.path.exists("test_verification.db"):
            os.remove("test_verification.db")

async def test_router_complex():
    """Test router with a complex query."""
    print("\n🔍 Testing Router with complex query...")
    
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sentinelrouter.sentinelrouter.router_logic import Router
    from sentinelrouter.sentinelrouter.database import Base
    
    # Create test database
    engine = create_engine("sqlite:///./test_verification.db")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        router = Router(db)
        
        result = await router.route(
            session_id="verification_test_complex",
            prompt="Explain the implications of quantum entanglement on information theory and computational complexity.",
            messages=[{"role": "user", "content": "Explain the implications of quantum entanglement on information theory and computational complexity."}]
        )
        
        print(f"✅ Router Response:")
        print(f"   Model Used: {result['model_used']}")
        print(f"   Response Length: {len(result['response'].content)} chars")
        print(f"   Complexity Score: {result['complexity_score']:.3f}")
        print(f"   Cost: ${result['cost']:.6f}")
        print(f"   Session Cost: ${result['session_cost']:.6f}")
        
        return True
    except Exception as e:
        print(f"❌ Router Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()
        # Cleanup test db
        if os.path.exists("test_verification.db"):
            os.remove("test_verification.db")

async def main():
    """Run all verification tests."""
    print("=" * 70)
    print("🚀 SentinelRouter Verification Script")
    print("=" * 70)
    print(f"\nConfiguration:")
    print(f"  DeepSeek Model: {settings.weak_model_id}")
    print(f"  Anthropic Model: {settings.strong_model_id}")
    print(f"  DeepSeek API Key: {'✅ Set' if settings.deepseek_api_key != 'dummy_key' else '❌ Not Set'}")
    print(f"  Anthropic API Key: {'✅ Set' if settings.anthropic_api_key != 'dummy_key' else '❌ Not Set'}")
    print()
    
    results = []
    
    # Test individual APIs
    results.append(("DeepSeek API", await test_deepseek()))
    results.append(("Anthropic API", await test_anthropic()))
    
    # Test router
    results.append(("Router Simple", await test_router_simple()))
    results.append(("Router Complex", await test_router_complex()))
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 Verification Summary")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All verifications passed! SentinelRouter is working correctly.")
        return 0
    else:
        print("\n⚠️  Some verifications failed. Check the errors above.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
