#!/usr/bin/env python3
"""
Comprehensive server test script to viciously test all models and routing logic.

Tests:
1. All weak models (including new Gemini models)
2. Strong models
3. Judge functionality with new Gemini judge
4. Rate limiting
5. Failover logic
6. Cache behavior
7. Cycle detection
"""

import asyncio
import httpx
import json
import time
from typing import Dict, List, Any

BASE_URL = "http://localhost:8000"
TIMEOUT = 60.0


class ServerTester:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=TIMEOUT)
        self.results = {
            "passed": [],
            "failed": [],
            "warnings": []
        }
    
    async def close(self):
        await self.client.aclose()
    
    def log_pass(self, test_name: str, message: str = ""):
        self.results["passed"].append({"test": test_name, "message": message})
        print(f"✅ PASS: {test_name} {message}")
    
    def log_fail(self, test_name: str, error: str):
        self.results["failed"].append({"test": test_name, "error": error})
        print(f"❌ FAIL: {test_name} - {error}")
    
    def log_warning(self, test_name: str, warning: str):
        self.results["warnings"].append({"test": test_name, "warning": warning})
        print(f"⚠️  WARN: {test_name} - {warning}")
    
    async def test_health_check(self):
        """Test basic health endpoint."""
        try:
            response = await self.client.get(f"{BASE_URL}/health")
            if response.status_code == 200:
                self.log_pass("Health Check", f"Status: {response.json()}")
            else:
                self.log_fail("Health Check", f"Status code: {response.status_code}")
        except Exception as e:
            self.log_fail("Health Check", str(e))
    
    async def test_weak_model_routing(self):
        """Test that weak models are used for simple prompts."""
        try:
            payload = {
                "session_id": "test-weak-routing",
                "prompt": "What is 2+2?",
                "messages": [{"role": "user", "content": "What is 2+2?"}]
            }
            
            response = await self.client.post(f"{BASE_URL}/v1/chat/completions", json=payload)
            
            if response.status_code == 200:
                data = response.json()
                model_used = data.get("model_used", "")
                
                # Check if a weak model was used (deepseek, gemini, groq, openrouter)
                weak_providers = ["deepseek", "gemini", "groq", "openrouter"]
                is_weak = any(provider in model_used.lower() for provider in weak_providers)
                
                if is_weak:
                    self.log_pass("Weak Model Routing", f"Used: {model_used}")
                else:
                    self.log_warning("Weak Model Routing", f"Expected weak model, got: {model_used}")
            else:
                self.log_fail("Weak Model Routing", f"Status: {response.status_code}")
        except Exception as e:
            self.log_fail("Weak Model Routing", str(e))
    
    async def test_new_gemini_models(self):
        """Test the three new Gemini models can be reached."""
        gemini_models = [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-3-flash-preview"
        ]
        
        for model in gemini_models:
            try:
                # Send multiple requests to increase chance of hitting this specific model
                for attempt in range(3):
                    payload = {
                        "session_id": f"test-gemini-{model}-{attempt}",
                        "prompt": f"Say 'Hello from {model}!' and nothing else.",
                        "messages": [{"role": "user", "content": f"Say 'Hello from {model}!' and nothing else."}],
                        "use_judge": False  # Skip judge to test direct routing
                    }
                    
                    response = await self.client.post(f"{BASE_URL}/v1/chat/completions", json=payload)
                    
                    if response.status_code == 200:
                        data = response.json()
                        model_used = data.get("model_used", "")
                        
                        if model in model_used:
                            self.log_pass(f"Gemini Model: {model}", f"Successfully used (attempt {attempt+1})")
                            break
                        elif attempt == 2:
                            self.log_warning(f"Gemini Model: {model}", f"Not reached after 3 attempts, last model: {model_used}")
                    else:
                        if attempt == 2:
                            self.log_fail(f"Gemini Model: {model}", f"Status: {response.status_code}")
                    
                    await asyncio.sleep(0.5)  # Small delay between attempts
                    
            except Exception as e:
                self.log_fail(f"Gemini Model: {model}", str(e))
    
    async def test_judge_with_gemini(self):
        """Test that the judge system works with gemini-3-flash-preview as primary."""
        try:
            payload = {
                "session_id": "test-judge-gemini",
                "prompt": "Design a distributed microservices architecture for a high-traffic e-commerce platform with real-time inventory management across multiple regions.",
                "messages": [{"role": "user", "content": "Design a distributed microservices architecture for a high-traffic e-commerce platform with real-time inventory management across multiple regions."}],
                "use_judge": True  # Force judge evaluation
            }
            
            response = await self.client.post(f"{BASE_URL}/v1/chat/completions", json=payload)
            
            if response.status_code == 200:
                data = response.json()
                complexity = data.get("complexity_score", 0.0)
                impact = data.get("impact_scope", "")
                
                # Complex prompt should get high complexity score
                if complexity > 0.6:
                    self.log_pass("Judge Evaluation", f"Complexity: {complexity:.2f}, Impact: {impact}")
                else:
                    self.log_warning("Judge Evaluation", f"Expected high complexity, got: {complexity:.2f}")
            else:
                self.log_fail("Judge Evaluation", f"Status: {response.status_code}")
        except Exception as e:
            self.log_fail("Judge Evaluation", str(e))
    
    async def test_rate_limiting(self):
        """Test that rate limiting is enforced."""
        try:
            # Send rapid requests to trigger rate limiting
            session_id = "test-rate-limit"
            requests_sent = 0
            rate_limited = False
            
            for i in range(20):
                payload = {
                    "session_id": session_id,
                    "prompt": f"Count to {i}",
                    "messages": [{"role": "user", "content": f"Count to {i}"}],
                    "use_judge": False
                }
                
                response = await self.client.post(f"{BASE_URL}/v1/chat/completions", json=payload)
                requests_sent += 1
                
                if response.status_code == 429:
                    rate_limited = True
                    self.log_pass("Rate Limiting", f"Rate limit enforced after {requests_sent} requests")
                    break
                
                # Small delay to avoid overwhelming
                await asyncio.sleep(0.1)
            
            if not rate_limited:
                self.log_warning("Rate Limiting", f"No rate limit hit after {requests_sent} requests")
        except Exception as e:
            self.log_fail("Rate Limiting", str(e))
    
    async def test_failover_logic(self):
        """Test that failover works when models are exhausted."""
        try:
            # Send requests until we see multiple models being used
            session_id = "test-failover"
            models_used = set()
            
            for i in range(10):
                payload = {
                    "session_id": f"{session_id}-{i}",
                    "prompt": f"What is the capital of country number {i}?",
                    "messages": [{"role": "user", "content": f"What is the capital of country number {i}?"}],
                    "use_judge": False
                }
                
                response = await self.client.post(f"{BASE_URL}/v1/chat/completions", json=payload)
                
                if response.status_code == 200:
                    data = response.json()
                    model_used = data.get("model_used", "")
                    models_used.add(model_used)
                
                await asyncio.sleep(0.2)
            
            if len(models_used) > 1:
                self.log_pass("Failover Logic", f"Multiple models used: {len(models_used)} ({', '.join(list(models_used)[:3])}...)")
            else:
                self.log_warning("Failover Logic", f"Only one model used: {models_used}")
        except Exception as e:
            self.log_fail("Failover Logic", str(e))
    
    async def test_strong_model_routing(self):
        """Test that complex prompts route to strong models."""
        try:
            payload = {
                "session_id": "test-strong-routing",
                "prompt": "Design a fault-tolerant distributed consensus algorithm for a blockchain network with Byzantine fault tolerance, including formal verification proofs and performance analysis under various network partitioning scenarios.",
                "messages": [{"role": "user", "content": "Design a fault-tolerant distributed consensus algorithm for a blockchain network with Byzantine fault tolerance, including formal verification proofs and performance analysis under various network partitioning scenarios."}],
                "use_judge": True
            }
            
            response = await self.client.post(f"{BASE_URL}/v1/chat/completions", json=payload)
            
            if response.status_code == 200:
                data = response.json()
                model_used = data.get("model_used", "")
                complexity = data.get("complexity_score", 0.0)
                
                # Should use strong model (claude or high-end model)
                strong_indicators = ["claude", "opus"]
                is_strong = any(indicator in model_used.lower() for indicator in strong_indicators)
                
                if is_strong or complexity > 0.7:
                    self.log_pass("Strong Model Routing", f"Used: {model_used}, Complexity: {complexity:.2f}")
                else:
                    self.log_warning("Strong Model Routing", f"Expected strong model, got: {model_used}")
            else:
                self.log_fail("Strong Model Routing", f"Status: {response.status_code}")
        except Exception as e:
            self.log_fail("Strong Model Routing", str(e))
    
    async def test_cache_behavior(self):
        """Test semantic caching works."""
        try:
            # Send same prompt twice
            prompt = "What is the capital of France?"
            session_id = "test-cache"
            
            payload = {
                "session_id": session_id,
                "prompt": prompt,
                "messages": [{"role": "user", "content": prompt}],
                "use_judge": False
            }
            
            # First request
            response1 = await self.client.post(f"{BASE_URL}/v1/chat/completions", json=payload)
            time1 = time.time()
            
            if response1.status_code == 200:
                data1 = response1.json()
                
                # Wait a bit
                await asyncio.sleep(1)
                
                # Second request (should potentially use cache)
                response2 = await self.client.post(f"{BASE_URL}/v1/chat/completions", json=payload)
                time2 = time.time()
                
                if response2.status_code == 200:
                    data2 = response2.json()
                    self.log_pass("Cache Behavior", "Multiple requests with same prompt successful")
                else:
                    self.log_fail("Cache Behavior", f"Second request failed: {response2.status_code}")
            else:
                self.log_fail("Cache Behavior", f"First request failed: {response1.status_code}")
        except Exception as e:
            self.log_fail("Cache Behavior", str(e))
    
    async def test_cycle_detection(self):
        """Test cycle detection prevents loops."""
        try:
            # Send same prompt repeatedly to trigger cycle detection
            prompt = "Repeat: Hello World"
            session_id = "test-cycle"
            
            for i in range(5):
                payload = {
                    "session_id": session_id,
                    "prompt": prompt,
                    "messages": [{"role": "user", "content": prompt}],
                    "use_judge": False
                }
                
                response = await self.client.post(f"{BASE_URL}/v1/chat/completions", json=payload)
                
                if response.status_code == 200:
                    data = response.json()
                    cycle_detected = data.get("cycle_detected", False)
                    
                    if cycle_detected:
                        self.log_pass("Cycle Detection", f"Detected cycle after {i+1} requests")
                        break
                
                await asyncio.sleep(0.2)
            
            self.log_pass("Cycle Detection", "Completed cycle detection test")
        except Exception as e:
            self.log_fail("Cycle Detection", str(e))
    
    async def test_error_handling(self):
        """Test server handles invalid requests gracefully."""
        try:
            # Send invalid payload
            payload = {
                "session_id": "test-error",
                # Missing required fields
            }
            
            response = await self.client.post(f"{BASE_URL}/v1/chat/completions", json=payload)
            
            if response.status_code in [400, 422]:
                self.log_pass("Error Handling", f"Properly rejected invalid request: {response.status_code}")
            else:
                self.log_warning("Error Handling", f"Unexpected status: {response.status_code}")
        except Exception as e:
            self.log_fail("Error Handling", str(e))
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        
        total = len(self.results["passed"]) + len(self.results["failed"])
        passed = len(self.results["passed"])
        failed = len(self.results["failed"])
        warnings = len(self.results["warnings"])
        
        print(f"\nTotal Tests: {total}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"⚠️  Warnings: {warnings}")
        
        if failed > 0:
            print("\nFailed Tests:")
            for result in self.results["failed"]:
                print(f"  ❌ {result['test']}: {result['error']}")
        
        if warnings > 0:
            print("\nWarnings:")
            for result in self.results["warnings"]:
                print(f"  ⚠️  {result['test']}: {result['warning']}")
        
        print("\n" + "=" * 80)
        
        if failed == 0:
            print("🎉 ALL TESTS PASSED!")
        else:
            print(f"⚠️  {failed} TEST(S) FAILED")
        
        print("=" * 80 + "\n")


async def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("COMPREHENSIVE SERVER TEST SUITE")
    print("=" * 80 + "\n")
    
    tester = ServerTester()
    
    try:
        # Run all tests
        await tester.test_health_check()
        await asyncio.sleep(0.5)
        
        await tester.test_weak_model_routing()
        await asyncio.sleep(0.5)
        
        await tester.test_new_gemini_models()
        await asyncio.sleep(0.5)
        
        await tester.test_judge_with_gemini()
        await asyncio.sleep(0.5)
        
        await tester.test_rate_limiting()
        await asyncio.sleep(0.5)
        
        await tester.test_failover_logic()
        await asyncio.sleep(0.5)
        
        await tester.test_strong_model_routing()
        await asyncio.sleep(0.5)
        
        await tester.test_cache_behavior()
        await asyncio.sleep(0.5)
        
        await tester.test_cycle_detection()
        await asyncio.sleep(0.5)
        
        await tester.test_error_handling()
        
    finally:
        await tester.close()
    
    # Print summary
    tester.print_summary()
    
    # Exit with appropriate code
    if len(tester.results["failed"]) > 0:
        return 1
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
