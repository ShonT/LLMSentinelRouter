"""
Demonstration Test: Backup Weak Models Feature

This test demonstrates how the backup weak models feature works
with automatic failover and circuit breaker pattern.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta

# Import the new components
import sys

sys.path.insert(0, "/Users/shonhitwork/Documents/unstuckRouter")

from sentinelrouter.sentinelrouter.model_registry import (
    ModelRegistry,
    ModelProvider,
    ModelTier,
    ProviderHealthTracker,
)
from sentinelrouter.sentinelrouter.clients import (
    LLMResponse,
    LLMClientError,
    BaseLLMClient,
)


# Mock client for testing
class MockLLMClient(BaseLLMClient):
    """Mock LLM client for testing."""

    def __init__(
        self, provider_id: str, should_fail: bool = False, fail_count: int = 0
    ):
        # Don't call super().__init__ to avoid needing real API keys
        self.provider_id = provider_id
        self.should_fail = should_fail
        self.fail_count = fail_count
        self.call_count = 0
        self.price_per_token = 0.0001

    async def chat_completion(self, messages):
        """Mock chat completion."""
        self.call_count += 1

        # Fail for first N calls
        if self.should_fail and self.call_count <= self.fail_count:
            raise LLMClientError(f"{self.provider_id} failed (call {self.call_count})")

        # Success after failures or if not failing
        return LLMResponse(
            content=f"Response from {self.provider_id}",
            model=self.provider_id,
            usage={"total_tokens": 100},
            cost=0.01,
        )


async def test_backup_weak_models_basic():
    """
    Test 1: Basic failover to backup weak model.

    Scenario:
    - Primary weak model fails
    - Automatically fails over to backup
    - Request succeeds
    """
    print("\n" + "=" * 70)
    print("TEST 1: Basic Failover to Backup")
    print("=" * 70)

    # Create registry
    registry = ModelRegistry()

    # Register primary (will fail)
    primary = ModelProvider(
        provider_id="deepseek-primary",
        tier=ModelTier.WEAK,
        client=MockLLMClient("deepseek-primary", should_fail=True, fail_count=999),
        priority=0,
    )
    registry.register_provider(primary)

    # Register backup (will succeed)
    backup = ModelProvider(
        provider_id="deepseek-backup",
        tier=ModelTier.WEAK,
        client=MockLLMClient("deepseek-backup", should_fail=False),
        priority=1,
    )
    registry.register_provider(backup)

    # Make request
    print("\n📤 Making request with primary failing...")
    response, provider_id = await registry.call_with_failover(
        tier=ModelTier.WEAK,
        messages=[{"role": "user", "content": "test"}],
        max_attempts=2,
    )

    # Verify backup was used
    print(f"✅ Response received from: {provider_id}")
    print(f"   Content: {response.content}")
    assert provider_id == "deepseek-backup"
    assert primary.client.call_count == 1  # Tried primary once
    assert backup.client.call_count == 1  # Used backup

    print("\n✅ TEST PASSED: Backup was automatically used")


async def test_circuit_breaker_opens():
    """
    Test 2: Circuit breaker opens after multiple failures.

    Scenario:
    - Make 3 requests to failing provider
    - Circuit breaker opens
    - Subsequent requests skip failing provider
    """
    print("\n" + "=" * 70)
    print("TEST 2: Circuit Breaker Pattern")
    print("=" * 70)

    # Create registry with low thresholds for testing
    health_tracker = ProviderHealthTracker(
        failure_threshold=3, cooldown_seconds=5  # Short for testing
    )
    registry = ModelRegistry(health_tracker=health_tracker)

    # Register failing primary
    primary = ModelProvider(
        provider_id="deepseek-primary",
        tier=ModelTier.WEAK,
        client=MockLLMClient("deepseek-primary", should_fail=True, fail_count=999),
        priority=0,
    )
    registry.register_provider(primary)

    # Register working backup
    backup = ModelProvider(
        provider_id="deepseek-backup",
        tier=ModelTier.WEAK,
        client=MockLLMClient("deepseek-backup", should_fail=False),
        priority=1,
    )
    registry.register_provider(backup)

    # Make 3 requests to trigger circuit breaker
    print("\n📤 Making 3 requests to trigger circuit breaker...")
    for i in range(3):
        response, provider_id = await registry.call_with_failover(
            tier=ModelTier.WEAK,
            messages=[{"role": "user", "content": f"request {i+1}"}],
            max_attempts=2,
        )
        print(f"   Request {i+1}: Used {provider_id}")

    # Check circuit breaker status
    status = health_tracker.get_status("deepseek-primary")
    print(f"\n🔴 Circuit Breaker Status for deepseek-primary:")
    print(f"   Available: {status['available']}")
    print(f"   Circuit Open: {status['circuit_open']}")
    print(f"   Failure Count: {status['failure_count']}")
    print(f"   Recent Failures: {status['recent_failures']}")

    # Verify circuit is open
    assert status["circuit_open"] == True
    assert status["available"] == False

    # Make another request - should skip primary entirely
    print(f"\n📤 Making request with circuit open...")
    response, provider_id = await registry.call_with_failover(
        tier=ModelTier.WEAK,
        messages=[{"role": "user", "content": "test"}],
        max_attempts=2,
    )

    # Verify backup was used immediately (didn't try primary)
    print(f"✅ Used {provider_id} (skipped primary with open circuit)")
    assert provider_id == "deepseek-backup"
    assert primary.client.call_count == 3  # Still 3 from before, not 4

    print("\n✅ TEST PASSED: Circuit breaker prevented retrying failed provider")


async def test_circuit_breaker_recovery():
    """
    Test 3: Circuit breaker closes after cooldown.

    Scenario:
    - Circuit opens due to failures
    - Wait for cooldown period
    - Circuit closes and retries provider
    """
    print("\n" + "=" * 70)
    print("TEST 3: Circuit Breaker Recovery")
    print("=" * 70)

    health_tracker = ProviderHealthTracker(
        failure_threshold=2, cooldown_seconds=2  # Very short for testing
    )
    registry = ModelRegistry(health_tracker=health_tracker)

    # Primary will fail 2 times, then succeed
    primary = ModelProvider(
        provider_id="deepseek-primary",
        tier=ModelTier.WEAK,
        client=MockLLMClient("deepseek-primary", should_fail=True, fail_count=2),
        priority=0,
    )
    registry.register_provider(primary)

    backup = ModelProvider(
        provider_id="deepseek-backup",
        tier=ModelTier.WEAK,
        client=MockLLMClient("deepseek-backup", should_fail=False),
        priority=1,
    )
    registry.register_provider(backup)

    # Trigger circuit breaker (2 failures)
    print("\n📤 Triggering circuit breaker with 2 failures...")
    for i in range(2):
        await registry.call_with_failover(
            ModelTier.WEAK, messages=[{"role": "user", "content": "test"}]
        )

    assert health_tracker.is_available("deepseek-primary") == False
    print("🔴 Circuit OPEN for deepseek-primary")

    # Wait for cooldown
    print("⏳ Waiting 3 seconds for cooldown...")
    await asyncio.sleep(3)

    # Circuit should be closed now
    assert health_tracker.is_available("deepseek-primary") == True
    print("🟢 Circuit CLOSED for deepseek-primary")

    # Make request - should try primary again and succeed
    print("\n📤 Making request after cooldown...")
    response, provider_id = await registry.call_with_failover(
        tier=ModelTier.WEAK,
        messages=[{"role": "user", "content": "test"}],
        max_attempts=2,
    )

    print(f"✅ Successfully used {provider_id} (primary recovered)")
    assert provider_id == "deepseek-primary"
    assert primary.client.call_count == 3  # 2 failures + 1 success

    print("\n✅ TEST PASSED: Circuit breaker recovered after cooldown")


async def test_three_tier_failover():
    """
    Test 4: Failover through 3 weak models.

    Scenario:
    - Primary fails
    - Backup 1 fails
    - Backup 2 succeeds
    """
    print("\n" + "=" * 70)
    print("TEST 4: Three-Tier Failover")
    print("=" * 70)

    registry = ModelRegistry()

    # Register 3 weak models
    models = [
        ("deepseek-primary", 0, True),  # Will fail
        ("deepseek-backup-1", 1, True),  # Will fail
        ("groq-llama3", 2, False),  # Will succeed
    ]

    for provider_id, priority, should_fail in models:
        provider = ModelProvider(
            provider_id=provider_id,
            tier=ModelTier.WEAK,
            client=MockLLMClient(provider_id, should_fail=should_fail, fail_count=999),
            priority=priority,
        )
        registry.register_provider(provider)
        print(
            f"   Registered: {provider_id} (priority={priority}, fails={should_fail})"
        )

    # Make request
    print("\n📤 Making request (first 2 will fail, 3rd will succeed)...")
    response, provider_id = await registry.call_with_failover(
        tier=ModelTier.WEAK,
        messages=[{"role": "user", "content": "test"}],
        max_attempts=3,
    )

    print(f"✅ Final provider used: {provider_id}")
    assert provider_id == "groq-llama3"

    # Verify all 3 were tried in order
    providers = registry._providers[ModelTier.WEAK]
    assert providers[0].client.call_count == 1  # Primary tried
    assert providers[1].client.call_count == 1  # Backup 1 tried
    assert providers[2].client.call_count == 1  # Backup 2 tried (success)

    print("\n✅ TEST PASSED: Successfully failed over through 3 providers")


async def main():
    """Run all demonstration tests."""
    print("\n" + "=" * 70)
    print("🧪 BACKUP WEAK MODELS FEATURE DEMONSTRATION")
    print("=" * 70)

    try:
        await test_backup_weak_models_basic()
        await test_circuit_breaker_opens()
        await test_circuit_breaker_recovery()
        await test_three_tier_failover()

        print("\n" + "=" * 70)
        print("✅✅✅ ALL TESTS PASSED ✅✅✅")
        print("=" * 70)
        print("\n📊 Summary:")
        print("   ✅ Basic failover works")
        print("   ✅ Circuit breaker prevents retry storms")
        print("   ✅ Circuit breaker recovers after cooldown")
        print("   ✅ Multiple backup tiers work correctly")
        print("\n🎯 The backup weak models feature is ready for production!")

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
