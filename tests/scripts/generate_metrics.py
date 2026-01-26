#!/usr/bin/env python3
"""
Make 3 test requests with different complexity levels.
"""

import httpx
import time

url = "http://localhost:8000/v1/chat/completions"

test_cases = [
    ("Simple math", "What is 5 + 3?"),
    ("Medium complexity", "Explain the basics of machine learning"),
    (
        "High complexity",
        "Design a microservices architecture for a real-time trading platform with 100k concurrent users",
    ),
]

print("=" * 70)
print("Making 3 test requests to generate metrics...")
print("=" * 70)

for i, (name, prompt) in enumerate(test_cases, 1):
    print(f"\n[{i}/3] {name}")
    print(f"Prompt: {prompt[:60]}...")

    payload = {
        "model": "gpt-4",
        "messages": [{"role": "user", "content": prompt}],
        "session_id": f"metrics-test-{i}",
    }

    try:
        start = time.time()
        with httpx.Client(timeout=120.0) as client:
            response = client.post(url, json=payload)

        duration = time.time() - start

        if response.status_code == 200:
            data = response.json()
            usage = data.get("usage", {})
            print(f"✅ Success in {duration:.1f}s")
            print(f"   Tokens: {usage.get('total_tokens', 'N/A')}")
            print(f"   Model: {data.get('model', 'unknown')}")
        else:
            print(f"❌ Error {response.status_code}: {response.text[:100]}")

    except Exception as e:
        print(f"❌ Exception: {e}")

    # Wait between requests
    if i < len(test_cases):
        print("   Waiting 3 seconds...")
        time.sleep(3)

print("\n" + "=" * 70)
print("All requests completed!")
print("=" * 70)
