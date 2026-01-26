#!/usr/bin/env python3
"""
Test client that mimics Roo's behavior to verify SentinelRouter connection.
"""
import httpx
import json

BASE_URL = "http://localhost:8000/v1"
SESSION_ID = "roo-test-client"


def test_connection():
    """Test basic connection to SentinelRouter."""
    client = httpx.Client(base_url=BASE_URL, timeout=60.0)

    # Test 1: List models (like OpenAI SDK does)
    print("🔍 Test 1: Listing models...")
    try:
        response = client.get("/models")
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print(f"   ✅ Models: {response.json()}")
        else:
            print(f"   ❌ Error: {response.text}")
    except Exception as e:
        print(f"   ❌ Exception: {e}")

    # Test 2: Send chat completion
    print("\n🔍 Test 2: Chat completion...")
    try:
        response = client.post(
            "/chat/completions",
            headers={"X-Session-ID": SESSION_ID},
            json={
                "model": "gpt-4",
                "messages": [
                    {"role": "user", "content": "Say 'test successful' in 3 words"}
                ],
            },
        )
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            print(f"   ✅ Response: {content}")
            print(f"   Model used: {response.headers.get('X-Sentinel-Model-Used')}")
            print(f"   Cost: ${response.headers.get('X-Sentinel-Cost')}")
        else:
            print(f"   ❌ Error: {response.text}")
    except Exception as e:
        print(f"   ❌ Exception: {e}")

    # Test 3: Check session
    print("\n🔍 Test 3: Session status...")
    try:
        response = client.get(f"http://localhost:8000/sessions/{SESSION_ID}")
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            session = response.json()
            print(f"   ✅ Session cost: ${session['current_cost']:.4f}")
            print(f"   Remaining: ${session['remaining_budget']:.2f}")
        else:
            print(f"   ❌ Error: {response.text}")
    except Exception as e:
        print(f"   ❌ Exception: {e}")

    client.close()
    print("\n✅ Test complete!")


if __name__ == "__main__":
    test_connection()
