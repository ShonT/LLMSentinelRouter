#!/usr/bin/env python3
"""
Quick verification that DeepSeek reasoner is working through the server.
"""

import httpx
import json

print("\n" + "="*70)
print("DEEPSEEK REASONER - FINAL VERIFICATION")
print("="*70 + "\n")

url = "http://localhost:8000/v1/chat/completions"
payload = {
    "session_id": "verification-test",
    "prompt": "What is the capital of France?",
    "messages": [{"role": "user", "content": "What is the capital of France?"}],
    "use_judge": False
}

try:
    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, json=payload)
        
        if response.status_code == 200:
            data = response.json()
            model = data.get("model", "unknown")
            content = data["choices"][0]["message"]["content"]
            
            print(f"✅ SUCCESS!\n")
            print(f"Model Used: {model}")
            print(f"Response: {content}\n")
            
            if model == "deepseek-reasoner":
                print("🎉 DeepSeek Reasoner is working correctly!")
            else:
                print(f"⚠️  Expected deepseek-reasoner, got {model}")
        else:
            print(f"❌ Error: Status {response.status_code}")
            print(f"Response: {response.text}")
            
except Exception as e:
    print(f"❌ Exception: {e}")

print("\n" + "="*70 + "\n")
