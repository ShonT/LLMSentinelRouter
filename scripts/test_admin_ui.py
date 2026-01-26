#!/usr/bin/env python3
"""
Test script for the new Admin UI API endpoints.

Tests:
1. GET /api/admin/policy - Fetch current policy configuration
2. POST /api/admin/policy - Update policy configuration
3. GET /api/admin/state - Fetch read-only state information
4. POST /api/admin/reset-cache - Reset semantic cache
5. POST /api/admin/reset-escalation - Reset escalation counters
"""

import asyncio
import httpx
import json
import sys
from typing import Dict, Any

BASE_URL = "http://localhost:8000"


def print_result(test_name: str, success: bool, data: Any = None, error: str = None):
    """Print test result in a formatted way."""
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"\n{status} {test_name}")
    if data:
        print(f"   Data: {json.dumps(data, indent=2)}")
    if error:
        print(f"   Error: {error}")


async def test_get_policy(client: httpx.AsyncClient):
    """Test GET /api/admin/policy endpoint."""
    try:
        response = await client.get(f"{BASE_URL}/api/admin/policy")
        if response.status_code == 200:
            data = response.json()
            print_result("GET /api/admin/policy", True, data)
            return data
        else:
            print_result("GET /api/admin/policy", False, error=f"Status {response.status_code}: {response.text}")
            return None
    except Exception as e:
        print_result("GET /api/admin/policy", False, error=str(e))
        return None


async def test_update_policy(client: httpx.AsyncClient):
    """Test POST /api/admin/policy endpoint."""
    try:
        # Test partial update - only update judge policy
        update_payload = {
            "judge": {
                "enabled": True,
                "mode": "smart",
                "complexity_threshold": 0.6
            }
        }
        
        response = await client.post(
            f"{BASE_URL}/api/admin/policy",
            json=update_payload
        )
        
        if response.status_code == 200:
            data = response.json()
            print_result("POST /api/admin/policy (update judge)", True, data)
            return data
        else:
            print_result("POST /api/admin/policy (update judge)", False, error=f"Status {response.status_code}: {response.text}")
            return None
    except Exception as e:
        print_result("POST /api/admin/policy (update judge)", False, error=str(e))
        return None


async def test_update_budget_control(client: httpx.AsyncClient):
    """Test POST /api/admin/policy with budget control update."""
    try:
        update_payload = {
            "budget_control": {
                "max_cost_per_session": 30.0,
                "escalation_rate_limit": 0.08,
                "rolling_window_size": 25
            }
        }
        
        response = await client.post(
            f"{BASE_URL}/api/admin/policy",
            json=update_payload
        )
        
        if response.status_code == 200:
            data = response.json()
            print_result("POST /api/admin/policy (update budget)", True, data)
            # Check for warnings
            if data.get("warnings"):
                print(f"   ⚠️  Warnings: {data['warnings']}")
            return data
        else:
            print_result("POST /api/admin/policy (update budget)", False, error=f"Status {response.status_code}: {response.text}")
            return None
    except Exception as e:
        print_result("POST /api/admin/policy (update budget)", False, error=str(e))
        return None


async def test_get_state(client: httpx.AsyncClient):
    """Test GET /api/admin/state endpoint."""
    try:
        response = await client.get(f"{BASE_URL}/api/admin/state")
        if response.status_code == 200:
            data = response.json()
            print_result("GET /api/admin/state", True, data)
            return data
        else:
            print_result("GET /api/admin/state", False, error=f"Status {response.status_code}: {response.text}")
            return None
    except Exception as e:
        print_result("GET /api/admin/state", False, error=str(e))
        return None


async def test_reset_cache(client: httpx.AsyncClient):
    """Test POST /api/admin/reset-cache endpoint."""
    try:
        response = await client.post(f"{BASE_URL}/api/admin/reset-cache")
        if response.status_code == 200:
            data = response.json()
            print_result("POST /api/admin/reset-cache", True, data)
            return data
        else:
            print_result("POST /api/admin/reset-cache", False, error=f"Status {response.status_code}: {response.text}")
            return None
    except Exception as e:
        print_result("POST /api/admin/reset-cache", False, error=str(e))
        return None


async def test_reset_escalation(client: httpx.AsyncClient):
    """Test POST /api/admin/reset-escalation endpoint."""
    try:
        response = await client.post(f"{BASE_URL}/api/admin/reset-escalation")
        if response.status_code == 200:
            data = response.json()
            print_result("POST /api/admin/reset-escalation", True, data)
            return data
        else:
            print_result("POST /api/admin/reset-escalation", False, error=f"Status {response.status_code}: {response.text}")
            return None
    except Exception as e:
        print_result("POST /api/admin/reset-escalation", False, error=str(e))
        return None


async def test_health_check(client: httpx.AsyncClient):
    """Test health check to verify server is running."""
    try:
        response = await client.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            print_result("Health Check", True, response.json())
            return True
        else:
            print_result("Health Check", False, error=f"Status {response.status_code}")
            return False
    except Exception as e:
        print_result("Health Check", False, error=str(e))
        return False


async def main():
    """Run all admin UI API tests."""
    print("=" * 80)
    print("Admin UI API Test Suite")
    print("=" * 80)
    print(f"\nTarget: {BASE_URL}")
    print("\nStarting tests...\n")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Test health check first
        if not await test_health_check(client):
            print("\n❌ Server not responding. Make sure the server is running on port 8000.")
            print("   Run: python -m sentinelrouter.sentinelrouter.server")
            sys.exit(1)
        
        # Test 1: Get current policy
        print("\n" + "=" * 80)
        print("Test 1: Get Current Policy")
        print("=" * 80)
        initial_policy = await test_get_policy(client)
        
        # Test 2: Update judge policy
        print("\n" + "=" * 80)
        print("Test 2: Update Judge Policy")
        print("=" * 80)
        await test_update_policy(client)
        
        # Test 3: Update budget control
        print("\n" + "=" * 80)
        print("Test 3: Update Budget Control")
        print("=" * 80)
        await test_update_budget_control(client)
        
        # Test 4: Get policy again to verify updates
        print("\n" + "=" * 80)
        print("Test 4: Verify Policy Updates")
        print("=" * 80)
        updated_policy = await test_get_policy(client)
        
        # Test 5: Get admin state
        print("\n" + "=" * 80)
        print("Test 5: Get Read-Only State")
        print("=" * 80)
        await test_get_state(client)
        
        # Test 6: Reset cache
        print("\n" + "=" * 80)
        print("Test 6: Reset Semantic Cache")
        print("=" * 80)
        await test_reset_cache(client)
        
        # Test 7: Reset escalation
        print("\n" + "=" * 80)
        print("Test 7: Reset Escalation Counters")
        print("=" * 80)
        await test_reset_escalation(client)
    
    print("\n" + "=" * 80)
    print("Test Suite Complete")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
