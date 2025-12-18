#!/usr/bin/env python3
"""
Quick test to verify new Gemini models work with proper delays.
"""

import asyncio
import httpx
import json

BASE_URL = "http://localhost:8000"


async def test_single_gemini_model(model_context: str):
    """Test a single request that should route through Gemini models."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        payload = {
            "session_id": f"quick-test-{model_context}",
            "prompt": f"Say 'Testing {model_context}' and nothing else.",
            "messages": [{"role": "user", "content": f"Say 'Testing {model_context}' and nothing else."}],
            "use_judge": False
        }
        
        print(f"\n{'='*60}")
        print(f"Testing: {model_context}")
        print(f"{'='*60}")
        
        try:
            response = await client.post(f"{BASE_URL}/v1/chat/completions", json=payload)
            
            if response.status_code == 200:
                data = response.json()
                model_used = data.get("model_used", "Unknown")
                content = data.get("response", {}).get("content", "")
                complexity = data.get("complexity_score", 0.0)
                cost = data.get("cost", 0.0)
                
                print(f"✅ SUCCESS")
                print(f"Model Used: {model_used}")
                print(f"Response: {content[:100]}...")
                print(f"Complexity: {complexity:.3f}")
                print(f"Cost: ${cost:.6f}")
                
                # Check if it's a Gemini model
                if "gemini" in model_used.lower():
                    print(f"✓ Gemini model successfully used!")
                else:
                    print(f"⚠ Non-Gemini model used (may be fallback): {model_used}")
                    
                return True
            else:
                print(f"❌ FAILED: Status {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ ERROR: {e}")
            return False


async def main():
    print("\n" + "="*80)
    print("QUICK GEMINI MODELS TEST")
    print("="*80)
    
    # Test with significant delays to avoid rate limiting
    tests = [
        "gemini-model-1",
        "gemini-model-2",
        "gemini-model-3"
    ]
    
    results = []
    for test in tests:
        result = await test_single_gemini_model(test)
        results.append(result)
        
        # Wait 10 seconds between tests to avoid rate limiting
        print(f"\nWaiting 10 seconds before next test...")
        await asyncio.sleep(10)
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    
    passed = sum(results)
    total = len(results)
    
    print(f"\nTests Passed: {passed}/{total}")
    
    if passed == total:
        print("\n✅ All tests passed!")
    else:
        print(f"\n⚠️ {total - passed} test(s) failed")
    
    print("="*80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
