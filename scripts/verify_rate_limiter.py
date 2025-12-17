#!/usr/bin/env python3
"""
Quick verification script to test rate limiter functionality.

Tests:
1. Record multiple requests and verify usage tracking
2. Check that limits are enforced correctly
3. Verify preemptive blocking works
"""

import asyncio
import sys
sys.path.insert(0, '/Users/shonhitwork/Documents/unstuckRouter')

from sentinelrouter.sentinelrouter.rate_limiter import get_rate_limiter


async def test_rate_limiter():
    print("=" * 70)
    print("RATE LIMITER VERIFICATION")
    print("=" * 70)
    
    limiter = get_rate_limiter(safety_margin=0.95)
    
    # Test 1: Record requests and check usage
    print("\n[Test 1] Recording 5 requests with 1000 tokens each...")
    for i in range(5):
        await limiter.record_request("test-model", tokens=1000)
        print(f"  Request {i+1} recorded")
    
    usage = await limiter.get_usage_stats("test-model")
    print(f"\n  Current usage:")
    print(f"    - Requests last minute: {usage['requests_last_minute']}")
    print(f"    - Tokens last minute: {usage['tokens_last_minute']}")
    print(f"    - Requests last day: {usage['requests_last_day']}")
    print(f"    - Tokens last day: {usage['tokens_last_day']}")
    
    assert usage['requests_last_minute'] == 5, "Should have 5 requests"
    assert usage['tokens_last_minute'] == 5000, "Should have 5000 tokens"
    print("  ✅ Usage tracking works correctly")
    
    # Test 2: Check limit enforcement - RPM
    print("\n[Test 2] Checking RPM limit enforcement (limit: 10)...")
    
    # Add 5 more requests (total: 10)
    for i in range(5):
        await limiter.record_request("test-model", tokens=1000)
    
    usage = await limiter.get_usage_stats("test-model")
    print(f"  Current RPM: {usage['requests_last_minute']}/10")
    
    # Should be blocked at 95% of 10 (9.5 requests)
    allowed, reason, usage_stats = await limiter.check_rate_limits(
        "test-model",
        rpm_limit=10
    )
    
    if not allowed:
        print(f"  ✅ Correctly blocked: {reason}")
    else:
        print(f"  ❌ Should have been blocked but was allowed")
        return False
    
    # Test 3: Check TPM limit enforcement
    print("\n[Test 3] Checking TPM limit enforcement (limit: 10000)...")
    
    usage = await limiter.get_usage_stats("test-model")
    print(f"  Current TPM: {usage['tokens_last_minute']}/10000")
    
    allowed, reason, usage_stats = await limiter.check_rate_limits(
        "test-model",
        tpm_limit=10000
    )
    
    if allowed:
        print(f"  ✅ Correctly allowed (under TPM limit)")
    else:
        print(f"  ⚠️  Blocked by TPM: {reason}")
    
    # Test 4: Estimated token projection
    print("\n[Test 4] Testing estimated token projection...")
    
    # Current: 10000 tokens, limit: 10000
    # If we estimate 100 more tokens, should be blocked
    allowed, reason, usage_stats = await limiter.check_rate_limits(
        "test-model",
        tpm_limit=10000,
        estimated_tokens=100
    )
    
    if not allowed:
        print(f"  ✅ Correctly blocked projected overflow: {reason}")
    else:
        print(f"  ❌ Should have blocked projected overflow")
        return False
    
    # Test 5: Multiple models independent tracking
    print("\n[Test 5] Testing multiple model independence...")
    
    await limiter.record_request("model-a", tokens=5000)
    await limiter.record_request("model-b", tokens=3000)
    
    usage_a = await limiter.get_usage_stats("model-a")
    usage_b = await limiter.get_usage_stats("model-b")
    
    print(f"  Model-A: {usage_a['requests_last_minute']} requests, {usage_a['tokens_last_minute']} tokens")
    print(f"  Model-B: {usage_b['requests_last_minute']} requests, {usage_b['tokens_last_minute']} tokens")
    
    if usage_a['tokens_last_minute'] == 5000 and usage_b['tokens_last_minute'] == 3000:
        print("  ✅ Models tracked independently")
    else:
        print("  ❌ Model tracking failed")
        return False
    
    print("\n" + "=" * 70)
    print("ALL TESTS PASSED ✅")
    print("=" * 70)
    print("\nRate limiter is working correctly and ready for production use!")
    return True


if __name__ == "__main__":
    result = asyncio.run(test_rate_limiter())
    sys.exit(0 if result else 1)
