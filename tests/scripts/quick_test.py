#!/usr/bin/env python3
"""
Simple test to generate one successful metric.
"""

import httpx
import json

url = "http://localhost:8000/v1/chat/completions"

payload = {
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Say hello"}],
    "session_id": "dashboard-test"
}

try:
    with httpx.Client(timeout=90.0) as client:
        print("Making request...")
        response = client.post(url, json=payload)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Success!")
            print(f"Response data: {json.dumps(data, indent=2)}")
        else:
            print(f"❌ Error {response.status_code}")
            print(response.text)
except Exception as e:
    print(f"❌ Exception: {e}")
