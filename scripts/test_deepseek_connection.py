#!/usr/bin/env python3
"""
Test DeepSeek API connection to diagnose authentication issues.
"""

import asyncio
import httpx
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sentinelrouter.sentinelrouter.config import get_settings


async def test_deepseek_api():
    """Test DeepSeek API with different model names."""
    
    settings = get_settings()
    api_key = settings.deepseek_api_key
    
    print("\n" + "="*70)
    print("DEEPSEEK API CONNECTION TEST")
    print("="*70)
    print(f"\nAPI Key: {api_key[:10]}...{api_key[-6:]}")
    print(f"Configured Model ID: {settings.weak_model_id}")
    print()
    
    # Test with different model names
    models_to_test = [
        "deepseek-reasoner",
        "deepseek-chat", 
        "deepseek-coder",
    ]
    
    base_url = "https://api.deepseek.com"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for model_name in models_to_test:
            print(f"\n{'='*70}")
            print(f"Testing model: {model_name}")
            print(f"{'='*70}")
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "user", "content": "Say 'Hello from DeepSeek!' and nothing else."}
                ],
                "stream": False,
            }
            
            try:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                
                print(f"Status Code: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    usage = data.get("usage", {})
                    
                    print(f"✅ SUCCESS!")
                    print(f"Response: {content}")
                    print(f"Model: {data.get('model', 'Unknown')}")
                    print(f"Usage: {usage}")
                    
                elif response.status_code == 401:
                    print(f"❌ AUTHENTICATION FAILED")
                    print(f"Response: {response.text}")
                    
                elif response.status_code == 404:
                    print(f"⚠️  MODEL NOT FOUND")
                    print(f"Response: {response.text}")
                    
                else:
                    print(f"❌ ERROR: {response.status_code}")
                    print(f"Response: {response.text}")
                    
            except Exception as e:
                print(f"❌ EXCEPTION: {type(e).__name__}: {e}")
    
    print("\n" + "="*70)
    print("TEST COMPLETE")
    print("="*70 + "\n")


if __name__ == "__main__":
    asyncio.run(test_deepseek_api())
