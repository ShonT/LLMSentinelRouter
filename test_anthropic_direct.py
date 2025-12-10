#!/usr/bin/env python3
"""Direct test of Anthropic API key with minimal context."""

import httpx
import json
import os
from pathlib import Path

# Load API key from .env
env_file = Path(__file__).parent / ".env"
api_key = None
model_id = None

with open(env_file) as f:
    for line in f:
        if line.startswith("ANTHROPIC_API_KEY="):
            api_key = line.split("=", 1)[1].strip()
        elif line.startswith("STRONG_MODEL_ID="):
            model_id = line.split("=", 1)[1].strip()

print(f"API Key: {api_key[:20]}...{api_key[-10:]}")
print(f"Model ID: {model_id}")

# Direct API call
url = "https://api.anthropic.com/v1/messages"
headers = {
    "x-api-key": api_key,
    "anthropic-version": "2023-06-01",
    "content-type": "application/json"
}

payload = {
    "model": model_id,
    "max_tokens": 100,
    "messages": [
        {"role": "user", "content": "Say 'Hello from Anthropic'"}
    ]
}

print(f"\nTesting with URL: {url}")
print(f"Headers: {headers}")
print(f"Payload: {json.dumps(payload, indent=2)}")

try:
    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, headers=headers, json=payload)
        print(f"\nStatus Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n✅ SUCCESS!")
            print(f"Content: {data['content'][0]['text']}")
        else:
            print(f"\n❌ FAILED!")
except Exception as e:
    print(f"\n❌ ERROR: {e}")
