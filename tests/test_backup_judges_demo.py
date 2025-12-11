"""
Test Backup Judges Feature

Demonstrates:
1. Primary judge success (DeepSeek)
2. Primary judge fails → backup judge succeeds (Anthropic)
3. Circuit breaker opens after 3 failures
4. Circuit breaker recovers after cooldown
5. All judges fail → default fallback
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta

from sentinelrouter.sentinelrouter.judge_registry import (
    JudgeRegistry,
    JudgeModel,
    JudgeHealthTracker,
    JudgeHealth,
)
from sentinelrouter.sentinelrouter.clients import BaseLLMClient, LLMResponse


def create_mock_client(
    model_id: str = "test-model",
    should_fail: bool = False,
    failure_message: str = "Mock failure"
):
    """Create a mock LLM client that can succeed or fail."""
    mock_client = MagicMock(spec=BaseLLMClient)
    mock_client.model_id = model_id
    
    if should_fail:
        async def failing_completion(*args, **kwargs):
            raise Exception(failure_message)
        mock_client.chat_completion = AsyncMock(side_effect=failing_completion)
    else:
        # Success case - return valid judge response
        async def successful_completion(*args, **kwargs):
            return LLMResponse(
                content='{"complexity_score": 0.3, "impact_scope": "LOW", "reasoning": "Simple task"}',
                model="test-model",
                usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
            )
        mock_client.chat_completion = AsyncMock(side_effect=successful_completion)
    
    return mock_client


@pytest.mark.asyncio
async def test_primary_judge_success():
    """Test 1: Primary judge succeeds on first attempt."""
    print("\n" + "="*60)
    print("TEST 1: Primary Judge Success")
    print("="*60)
    
    # Setup
    registry = JudgeRegistry()
    
    primary_client = create_mock_client("deepseek-test", should_fail=False)
    primary_judge = JudgeModel(
        judge_id="primary",
        client=primary_client,
        priority=0,
        display_name="Primary Judge"
    )
    registry.register_judge(primary_judge)
    
    # Execute
    score, impact, reasoning, judge_id = await registry.judge_with_failover(
        "Simple hello world task"
    )
    
    # Assert
    assert judge_id == "primary", "Should use primary judge"
    assert score == 0.3
    assert impact == "LOW"
    assert "Simple task" in reasoning
    
    # Check health
    status = registry.health_tracker.get_status("primary")
    assert status["failure_count"] == 0
    assert status["available"] is True
    
    print("✅ Primary judge succeeded")
    print(f"   Score: {score}, Impact: {impact}")
    print(f"   Judge Used: {judge_id}")
    print(f"   Health: {status}")


@pytest.mark.asyncio
async def test_primary_fails_backup_succeeds():
    """Test 2: Primary judge fails, backup judge succeeds."""
    print("\n" + "="*60)
    print("TEST 2: Primary Fails → Backup Succeeds")
    print("="*60)
    
    # Setup
    registry = JudgeRegistry()
    
    # Primary fails
    primary_client = create_mock_client(
        "deepseek-test",
        should_fail=True,
        failure_message="Primary judge unavailable"
    )
    primary_judge = JudgeModel(
        judge_id="primary",
        client=primary_client,
        priority=0,
        display_name="Primary Judge"
    )
    registry.register_judge(primary_judge)
    
    # Backup succeeds
    backup_client = create_mock_client("anthropic-test", should_fail=False)
    backup_judge = JudgeModel(
        judge_id="backup",
        client=backup_client,
        priority=1,
        display_name="Backup Judge"
    )
    registry.register_judge(backup_judge)
    
    # Execute
    score, impact, reasoning, judge_id = await registry.judge_with_failover(
        "Some task to evaluate"
    )
    
    # Assert
    assert judge_id == "backup", "Should failover to backup judge"
    assert score == 0.3
    assert impact == "LOW"
    
    # Check health
    primary_status = registry.health_tracker.get_status("primary")
    backup_status = registry.health_tracker.get_status("backup")
    
    assert primary_status["failure_count"] == 1, "Primary should have 1 failure"
    assert backup_status["failure_count"] == 0, "Backup should have 0 failures"
    
    print("✅ Automatic failover worked!")
    print(f"   Primary failures: {primary_status['failure_count']}")
    print(f"   Backup used: {judge_id}")
    print(f"   Result: score={score}, impact={impact}")


@pytest.mark.asyncio
async def test_circuit_breaker_opens():
    """Test 3: Circuit breaker opens after 3 failures in 5 minutes."""
    print("\n" + "="*60)
    print("TEST 3: Circuit Breaker Opens After 3 Failures")
    print("="*60)
    
    # Setup with strict circuit breaker
    health_tracker = JudgeHealthTracker(failure_threshold=3, cooldown_seconds=60)
    registry = JudgeRegistry(health_tracker=health_tracker)
    
    # Primary always fails
    primary_client = create_mock_client(
        "deepseek-test",
        should_fail=True,
        failure_message="Service unavailable"
    )
    primary_judge = JudgeModel(
        judge_id="primary",
        client=primary_client,
        priority=0,
        display_name="Primary Judge"
    )
    registry.register_judge(primary_judge)
    
    # Backup succeeds
    backup_client = create_mock_client("backup-test", should_fail=False)
    backup_judge = JudgeModel(
        judge_id="backup",
        client=backup_client,
        priority=1,
        display_name="Backup Judge"
    )
    registry.register_judge(backup_judge)
    
    # Execute: Make 3 requests to trigger circuit breaker
    print("\nMaking 3 requests to trigger circuit breaker...")
    for i in range(3):
        score, impact, reasoning, judge_id = await registry.judge_with_failover(
            f"Request {i+1}"
        )
        assert judge_id == "backup", f"Request {i+1} should use backup"
        print(f"   Request {i+1}: Used {judge_id}")
    
    # Check circuit breaker status
    primary_status = registry.health_tracker.get_status("primary")
    print(f"\n⚡ Circuit Breaker Status:")
    print(f"   Failures: {primary_status['failure_count']}")
    print(f"   Recent failures: {primary_status['recent_failures']}")
    print(f"   Circuit open: {primary_status['circuit_open']}")
    print(f"   Available: {primary_status['available']}")
    
    assert primary_status["circuit_open"] is True, "Circuit should be open"
    assert primary_status["available"] is False, "Primary should be unavailable"
    assert primary_status["recent_failures"] == 3, "Should have 3 recent failures"
    
    # Execute: Next request should skip primary entirely
    print("\nMaking request 4 (circuit open)...")
    score, impact, reasoning, judge_id = await registry.judge_with_failover(
        "Request 4 - circuit open"
    )
    
    # Primary should NOT be attempted (circuit open)
    assert judge_id == "backup", "Should skip primary (circuit open)"
    assert primary_status["failure_count"] == 3, "Failure count unchanged"
    
    print("✅ Circuit breaker opened successfully!")
    print(f"   Primary judge protected from further attempts")
    print(f"   All traffic routed to backup judge")


@pytest.mark.asyncio
async def test_circuit_breaker_recovers():
    """Test 4: Circuit breaker closes after cooldown period."""
    print("\n" + "="*60)
    print("TEST 4: Circuit Breaker Recovers After Cooldown")
    print("="*60)
    
    # Setup with SHORT cooldown for testing
    health_tracker = JudgeHealthTracker(failure_threshold=2, cooldown_seconds=1)
    registry = JudgeRegistry(health_tracker=health_tracker)
    
    # Primary fails initially, then succeeds
    call_count = {"count": 0}
    
    def create_flaky_client():
        """Client that fails first 2 times, then succeeds."""
        mock_client = MagicMock(spec=BaseLLMClient)
        mock_client.model_id = "flaky-judge"
        
        async def flaky_completion(*args, **kwargs):
            call_count["count"] += 1
            if call_count["count"] <= 2:
                raise Exception(f"Failure {call_count['count']}")
            # Success after 2 failures
            return LLMResponse(
                content='{"complexity_score": 0.4, "impact_scope": "MEDIUM", "reasoning": "Recovered"}',
                model="flaky-judge",
                usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
            )
        
        mock_client.chat_completion = AsyncMock(side_effect=flaky_completion)
        return mock_client
    
    primary_client = create_flaky_client()
    primary_judge = JudgeModel(
        judge_id="primary",
        client=primary_client,
        priority=0,
        display_name="Primary Judge"
    )
    registry.register_judge(primary_judge)
    
    # Backup always succeeds
    backup_client = create_mock_client("backup-test", should_fail=False)
    backup_judge = JudgeModel(
        judge_id="backup",
        client=backup_client,
        priority=1,
        display_name="Backup Judge"
    )
    registry.register_judge(backup_judge)
    
    # Step 1: Trigger circuit breaker (2 failures)
    print("\nStep 1: Triggering circuit breaker...")
    for i in range(2):
        await registry.judge_with_failover(f"Request {i+1}")
        print(f"   Request {i+1}: Primary failed, backup used")
    
    status = registry.health_tracker.get_status("primary")
    print(f"\n⚡ Circuit opened: {status['circuit_open']}")
    assert status["circuit_open"] is True, "Circuit should be open"
    
    # Step 2: Wait for cooldown
    print(f"\nStep 2: Waiting {1.2}s for cooldown...")
    await asyncio.sleep(1.2)  # Wait slightly longer than cooldown
    
    status = registry.health_tracker.get_status("primary")
    print(f"⏱️  Circuit after cooldown: open={status['circuit_open']}")
    assert status["circuit_open"] is False, "Circuit should close after cooldown"
    
    # Step 3: Primary should be tried again and succeed
    print("\nStep 3: Making request after cooldown...")
    score, impact, reasoning, judge_id = await registry.judge_with_failover(
        "Request after cooldown"
    )
    
    assert judge_id == "primary", "Should try primary again after cooldown"
    assert score == 0.4
    assert "Recovered" in reasoning
    
    status = registry.health_tracker.get_status("primary")
    print(f"\n✅ Circuit breaker recovered!")
    print(f"   Judge used: {judge_id}")
    print(f"   Failures reset: {status['failure_count']}")
    print(f"   Circuit open: {status['circuit_open']}")
    
    assert status["failure_count"] == 0, "Failures should be reset after success"


@pytest.mark.asyncio
async def test_all_judges_fail_fallback():
    """Test 5: All judges fail → use default fallback."""
    print("\n" + "="*60)
    print("TEST 5: All Judges Fail → Default Fallback")
    print("="*60)
    
    # Setup
    registry = JudgeRegistry()
    
    # Both judges fail
    primary_client = create_mock_client(
        "primary-test",
        should_fail=True,
        failure_message="Primary unavailable"
    )
    primary_judge = JudgeModel(
        judge_id="primary",
        client=primary_client,
        priority=0,
        display_name="Primary Judge"
    )
    registry.register_judge(primary_judge)
    
    backup_client = create_mock_client(
        "backup-test",
        should_fail=True,
        failure_message="Backup unavailable"
    )
    backup_judge = JudgeModel(
        judge_id="backup",
        client=backup_client,
        priority=1,
        display_name="Backup Judge"
    )
    registry.register_judge(backup_judge)
    
    # Execute
    score, impact, reasoning, judge_id = await registry.judge_with_failover(
        "Request when all judges down",
        max_attempts=3
    )
    
    # Assert
    assert judge_id == "fallback", "Should use fallback when all fail"
    assert score == 0.5, "Default fallback score"
    assert impact == "LOW", "Default fallback impact"
    assert "All judges failed" in reasoning
    
    print("✅ Fallback mechanism working!")
    print(f"   Judge: {judge_id}")
    print(f"   Default score: {score}")
    print(f"   Default impact: {impact}")
    print(f"   Reasoning: {reasoning[:60]}...")
    
    # Check both judges recorded failures
    primary_status = registry.health_tracker.get_status("primary")
    backup_status = registry.health_tracker.get_status("backup")
    
    print(f"\n📊 Health Status:")
    print(f"   Primary failures: {primary_status['failure_count']}")
    print(f"   Backup failures: {backup_status['failure_count']}")
    
    assert primary_status["failure_count"] >= 1
    assert backup_status["failure_count"] >= 1


@pytest.mark.asyncio
async def test_judge_registry_status():
    """Test 6: Registry status reporting."""
    print("\n" + "="*60)
    print("TEST 6: Judge Registry Status Reporting")
    print("="*60)
    
    # Setup
    registry = JudgeRegistry()
    
    primary_client = create_mock_client("primary-test", should_fail=False)
    primary_judge = JudgeModel(
        judge_id="primary",
        client=primary_client,
        priority=0,
        display_name="Primary DeepSeek Judge"
    )
    registry.register_judge(primary_judge)
    
    backup_client = create_mock_client("backup-test", should_fail=False)
    backup_judge = JudgeModel(
        judge_id="backup",
        client=backup_client,
        priority=1,
        display_name="Backup Anthropic Judge"
    )
    registry.register_judge(backup_judge)
    
    # Make a successful request
    await registry.judge_with_failover("Test request")
    
    # Get status
    status = registry.get_registry_status()
    
    print("\n📊 Registry Status:")
    for judge_info in status["judges"]:
        print(f"\n   Judge: {judge_info['display_name']}")
        print(f"   - ID: {judge_info['judge_id']}")
        print(f"   - Priority: {judge_info['priority']}")
        print(f"   - Model: {judge_info['model']}")
        print(f"   - Available: {judge_info['available']}")
        print(f"   - Circuit Open: {judge_info['circuit_open']}")
        print(f"   - Failures: {judge_info['failure_count']}")
    
    assert len(status["judges"]) == 2, "Should have 2 judges"
    assert status["judges"][0]["judge_id"] == "primary"
    assert status["judges"][0]["available"] is True
    assert status["judges"][1]["judge_id"] == "backup"
    
    print("\n✅ Status reporting working correctly!")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("BACKUP JUDGES DEMONSTRATION")
    print("="*60)
    print("Running comprehensive tests of backup judge system...")
    print("="*60)
    
    async def run_all_tests():
        await test_primary_judge_success()
        await test_primary_fails_backup_succeeds()
        await test_circuit_breaker_opens()
        await test_circuit_breaker_recovers()
        await test_all_judges_fail_fallback()
        await test_judge_registry_status()
        
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED!")
        print("="*60)
        print("\nBackup Judge Features Verified:")
        print("  ✓ Primary judge success path")
        print("  ✓ Automatic failover to backup")
        print("  ✓ Circuit breaker opens after failures")
        print("  ✓ Circuit breaker recovers after cooldown")
        print("  ✓ Default fallback when all judges fail")
        print("  ✓ Status reporting and health monitoring")
        print("="*60 + "\n")
    
    asyncio.run(run_all_tests())
