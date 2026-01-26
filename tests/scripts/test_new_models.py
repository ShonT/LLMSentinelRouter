#!/usr/bin/env python3
"""
Test script to verify new model configuration and throttle banning system.
Sends 5 requests with varying complexity to test all model tiers.
"""
import requests
import json
import time

API_URL = "http://localhost:8000/v1/chat/completions"

test_requests = [
    {
        "name": "Simple Math (Should use weak model)",
        "messages": [{"role": "user", "content": "What is 15 + 27?"}],
        "expected_tier": "weak",
    },
    {
        "name": "Code Explanation (Should use weak model)",
        "messages": [
            {
                "role": "user",
                "content": "Explain what a Python decorator is in 2 sentences",
            }
        ],
        "expected_tier": "weak",
    },
    {
        "name": "Complex Algorithm (Might use strong model)",
        "messages": [
            {
                "role": "user",
                "content": "Design a distributed rate limiting algorithm for a microservices architecture with multiple regions",
            }
        ],
        "expected_tier": "strong or weak",
    },
    {
        "name": "Architecture Design (Should use strong model)",
        "messages": [
            {
                "role": "user",
                "content": "Design a complete event-driven architecture for a real-time trading system with 100k TPS, explain data flow, failure recovery, and consistency guarantees",
            }
        ],
        "expected_tier": "strong",
    },
    {
        "name": "Quick Question (Should use weak model)",
        "messages": [{"role": "user", "content": "What does HTTP stand for?"}],
        "expected_tier": "weak",
    },
]


def send_request(test_case, index):
    """Send a single test request and display results."""
    print(f"\n{'='*80}")
    print(f"Test {index + 1}: {test_case['name']}")
    print(f"Expected tier: {test_case['expected_tier']}")
    print(f"{'='*80}")

    start_time = time.time()

    try:
        response = requests.post(
            API_URL,
            json={"model": "sentinel-router", "messages": test_case["messages"]},
            headers={"Content-Type": "application/json"},
            timeout=120,
        )

        elapsed = time.time() - start_time

        if response.status_code == 200:
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            model_used = data.get("model", "unknown")

            print(f"✅ SUCCESS ({elapsed:.2f}s)")
            print(f"Model used: {model_used}")
            print(f"Response preview: {content[:150]}...")

            # Check for usage metadata
            usage = data.get("usage", {})
            if usage:
                print(
                    f"Tokens - prompt: {usage.get('prompt_tokens')}, completion: {usage.get('completion_tokens')}, total: {usage.get('total_tokens')}"
                )

        else:
            print(f"❌ ERROR: {response.status_code}")
            print(f"Response: {response.text}")

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ EXCEPTION after {elapsed:.2f}s: {e}")


def main():
    """Run all test cases."""
    print("=" * 80)
    print("Testing New Model Configuration + Throttle Banning")
    print("=" * 80)
    print(f"API URL: {API_URL}")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Total tests: {len(test_requests)}")

    for i, test_case in enumerate(test_requests):
        send_request(test_case, i)
        if i < len(test_requests) - 1:
            # Small delay between requests
            time.sleep(2)

    print("\n" + "=" * 80)
    print("All tests completed!")
    print("Check metrics dashboard at http://localhost:8001/dashboard")
    print("=" * 80)


if __name__ == "__main__":
    main()
