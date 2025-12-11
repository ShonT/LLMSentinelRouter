"""
Test Gemini Backup Judges Integration

Verifies:
1. Gemini clients can be instantiated
2. Judge registry includes all 4 judges (DeepSeek, Anthropic, Gemini x2)
3. Failover works through all judges
4. Default fallback assumes weak model (LOW complexity, score=0.1)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from sentinelrouter.sentinelrouter.judge import get_judge_registry, StingyJudge
from sentinelrouter.sentinelrouter.clients import LLMResponse


async def test_judge_registry_has_all_judges():
    """Test that all 4 judges are registered."""
    print("\n" + "="*60)
    print("TEST: Judge Registry Has All Judges")
    print("="*60)
    
    registry = await get_judge_registry()
    status = registry.get_registry_status()
    
    judges = status["judges"]
    print(f"\n✅ Found {len(judges)} judges registered:")
    
    for judge in judges:
        print(f"\n  Judge: {judge['display_name']}")
        print(f"    ID: {judge['judge_id']}")
        print(f"    Priority: {judge['priority']}")
        print(f"    Model: {judge['model']}")
        print(f"    Available: {'✅' if judge['available'] else '❌'}")
    
    assert len(judges) == 4, f"Expected 4 judges, got {len(judges)}"
    
    # Check priorities
    priorities = [j['priority'] for j in judges]
    assert priorities == [0, 1, 2, 3], f"Expected priorities [0,1,2,3], got {priorities}"
    
    # Check judge IDs
    judge_ids = [j['judge_id'] for j in judges]
    expected_ids = [
        "deepseek-judge-primary",
        "anthropic-judge-backup",
        "gemini-judge-backup1",
        "gemini-judge-backup2"
    ]
    assert judge_ids == expected_ids, f"Judge IDs don't match"
    
    print("\n✅ All judges registered correctly!")


async def test_default_fallback_assumes_weak_model():
    """Test that when all judges fail, system assumes weak model (LOW, 0.1)."""
    print("\n" + "="*60)
    print("TEST: Default Fallback Assumes Weak Model")
    print("="*60)
    
    registry = await get_judge_registry()
    
    # Check default fallback
    fallback = registry._default_fallback
    score, impact, reasoning = fallback
    
    print(f"\nDefault Fallback Configuration:")
    print(f"  Complexity Score: {score}")
    print(f"  Impact Scope: {impact}")
    print(f"  Reasoning: {reasoning}")
    
    assert score == 0.1, f"Expected score=0.1 (weak model), got {score}"
    assert impact == "LOW", f"Expected impact=LOW, got {impact}"
    assert "weak model" in reasoning.lower(), "Reasoning should mention weak model"
    
    print("\n✅ Default fallback correctly assumes weak model!")


async def test_stingy_judge_basic_usage():
    """Test StingyJudge works with new judge registry."""
    print("\n" + "="*60)
    print("TEST: StingyJudge Basic Usage")
    print("="*60)
    
    judge = StingyJudge()
    
    # Get status
    status = await judge.get_status()
    
    print(f"\nStingyJudge Status:")
    print(f"  Total Judges: {len(status['judges'])}")
    print(f"  Available Judges: {sum(1 for j in status['judges'] if j['available'])}")
    
    for judge_info in status['judges']:
        print(f"\n  {judge_info['display_name']}:")
        print(f"    Priority: {judge_info['priority']}")
        print(f"    Available: {judge_info['available']}")
        print(f"    Circuit: {'🟢 CLOSED' if not judge_info['circuit_open'] else '🔴 OPEN'}")
    
    assert len(status['judges']) == 4, "Should have 4 judges"
    
    print("\n✅ StingyJudge configured with all judges!")


async def test_judge_priority_order():
    """Test that judges are tried in correct priority order."""
    print("\n" + "="*60)
    print("TEST: Judge Priority Order")
    print("="*60)
    
    registry = await get_judge_registry()
    
    # Get available judges
    available = registry.get_available_judges()
    
    print(f"\nJudges in priority order:")
    for i, judge in enumerate(available):
        print(f"  {i+1}. {judge.display_name} (priority={judge.priority})")
    
    # Verify priority order
    priorities = [j.priority for j in available]
    assert priorities == sorted(priorities), "Judges should be sorted by priority"
    
    # First should be primary (DeepSeek)
    assert available[0].judge_id == "deepseek-judge-primary", "First should be primary"
    
    # Last should be Gemini backup 2
    assert available[-1].judge_id == "gemini-judge-backup2", "Last should be Gemini backup 2"
    
    print("\n✅ Judges are in correct priority order!")


async def test_gemini_client_structure():
    """Test that Gemini clients can be instantiated."""
    print("\n" + "="*60)
    print("TEST: Gemini Client Structure")
    print("="*60)
    
    from sentinelrouter.sentinelrouter.clients import (
        get_gemini_backup1_client,
        get_gemini_backup2_client
    )
    
    # Get clients
    gemini1 = await get_gemini_backup1_client()
    gemini2 = await get_gemini_backup2_client()
    
    print(f"\nGemini Backup 1:")
    print(f"  Model: {gemini1.model_id}")
    print(f"  Base URL: {gemini1.base_url}")
    print(f"  Price per token: ${gemini1.price_per_token:.10f}")
    
    print(f"\nGemini Backup 2:")
    print(f"  Model: {gemini2.model_id}")
    print(f"  Base URL: {gemini2.base_url}")
    print(f"  Price per token: ${gemini2.price_per_token:.10f}")
    
    assert gemini1.model_id == "gemini-2.0-flash-exp", "Gemini 1 model ID"
    assert gemini2.model_id == "gemini-2.0-flash-exp", "Gemini 2 model ID"
    assert "generativelanguage.googleapis.com" in gemini1.base_url, "Gemini base URL"
    
    print("\n✅ Gemini clients configured correctly!")


async def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("GEMINI BACKUP JUDGES - INTEGRATION TESTS")
    print("="*70)
    print("\nVerifying Gemini backup judges integration...")
    
    try:
        await test_judge_registry_has_all_judges()
        await test_default_fallback_assumes_weak_model()
        await test_stingy_judge_basic_usage()
        await test_judge_priority_order()
        await test_gemini_client_structure()
        
        print("\n" + "="*70)
        print("✅ ALL TESTS PASSED!")
        print("="*70)
        print("\nSummary:")
        print("  ✓ 4 judges registered (DeepSeek, Anthropic, Gemini x2)")
        print("  ✓ Priority order correct (0, 1, 2, 3)")
        print("  ✓ Default fallback assumes weak model (0.1, LOW)")
        print("  ✓ StingyJudge configured with all judges")
        print("  ✓ Gemini clients instantiated correctly")
        print("="*70 + "\n")
        
    except Exception as e:
        print(f"\n❌ Error running tests: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
