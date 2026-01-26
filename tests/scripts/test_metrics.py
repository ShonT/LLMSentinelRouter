#!/usr/bin/env python3
"""
Test script to generate metrics by making requests to the router.
"""

import httpx
import asyncio
import json

BASE_URL = "http://localhost:8000/v1"


async def make_test_request(session_id: str, prompt: str):
    """Make a single test request to the router."""
    url = f"{BASE_URL}/chat/completions"

    payload = {
        "model": "gpt-4",
        "messages": [{"role": "user", "content": prompt}],
        "session_id": session_id,
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            print(f"Making request: {prompt[:50]}...")
            response = await client.post(url, json=payload)

            if response.status_code == 200:
                data = response.json()
                print(f"✅ Success! Model: {data.get('model_used', 'unknown')}")
                return data
            else:
                print(f"❌ Error: {response.status_code}")
                print(response.text)
                return None
    except Exception as e:
        print(f"❌ Exception: {e}")
        return None


async def main():
    """Run multiple test requests."""
    print("=" * 60)
    print("SentinelRouter Metrics Test")
    print("=" * 60)

    # Test 1: Simple question (should use weak model)
    print("\nTest 1: Simple question")
    await make_test_request("test-session-1", "What is 2+2?")

    await asyncio.sleep(2)

    # Test 2: More complex question
    print("\nTest 2: Medium complexity")
    await make_test_request("test-session-1", "Explain quantum computing in detail")

    await asyncio.sleep(2)

    # Test 3: High complexity question
    print("\nTest 3: High complexity")
    await make_test_request(
        "test-session-1",
        "Design a distributed system architecture for a global e-commerce platform handling 1M transactions per second",
    )

    print("\n" + "=" * 60)
    print("Tests complete! Check dashboard at http://localhost:8001")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
