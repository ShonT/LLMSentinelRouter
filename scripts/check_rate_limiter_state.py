#!/usr/bin/env python3
"""Check rate limiter state after the test request."""
import asyncio
import sys
sys.path.insert(0, '/Users/shonhitwork/Documents/unstuckRouter')

from sentinelrouter.sentinelrouter.rate_limiter import get_rate_limiter

async def check_state():
    limiter = get_rate_limiter()
    
    # Check deepseek-chat usage (model used in test request)
    usage = await limiter.get_usage_stats("deepseek-chat")
    
    print("=" * 60)
    print("RATE LIMITER STATE AFTER TEST REQUEST")
    print("=" * 60)
    print(f"\nModel: deepseek-chat")
    print(f"  Requests (last minute): {usage['requests_last_minute']}")
    print(f"  Tokens (last minute):   {usage['tokens_last_minute']}")
    print(f"  Requests (last day):    {usage['requests_last_day']}")
    print(f"  Tokens (last day):      {usage['tokens_last_day']}")
    print()
    
    if usage['requests_last_minute'] > 0:
        print("✅ Rate limiter successfully recorded the test request!")
        print(f"   Expected: 91 tokens (9 prompt + 82 completion)")
        print(f"   Actual:   {usage['tokens_last_minute']} tokens")
    else:
        print("⚠️  No usage recorded (rate limiter may not be active)")
    
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(check_state())
