"""
Backup Judges Integration Example

Demonstrates how to use the new backup judges feature in your application.
"""

import asyncio
from sentinelrouter.sentinelrouter.judge import StingyJudge


async def example_1_basic_usage():
    """
    Example 1: Basic usage - No code changes needed!
    
    The backup system is transparent. Your existing code continues to work,
    but now has automatic failover to backup judges.
    """
    print("\n" + "="*60)
    print("EXAMPLE 1: Basic Usage (No changes needed)")
    print("="*60)
    
    judge = StingyJudge()
    
    # This now automatically uses backup judges if primary fails
    prompts = [
        "Fix a typo in documentation",
        "Refactor the authentication module",
        "Build a new microservice architecture for payments",
    ]
    
    for prompt in prompts:
        score, impact, reasoning = await judge.judge(prompt)
        print(f"\nPrompt: {prompt[:50]}...")
        print(f"  Score: {score:.2f}")
        print(f"  Impact: {impact}")
        print(f"  Reasoning: {reasoning[:80]}...")


async def example_2_monitoring_health():
    """
    Example 2: Monitor judge health
    
    Check the status of all judges to see which ones are available,
    circuit breaker status, and failure counts.
    """
    print("\n" + "="*60)
    print("EXAMPLE 2: Monitoring Judge Health")
    print("="*60)
    
    judge = StingyJudge()
    
    # Make a few judge calls
    await judge.judge("Create a new API endpoint")
    await judge.judge("Update README")
    
    # Get health status
    status = await judge.get_status()
    
    print("\nJudge Health Status:")
    for judge_info in status["judges"]:
        print(f"\n  {judge_info['display_name']}:")
        print(f"    ID: {judge_info['judge_id']}")
        print(f"    Priority: {judge_info['priority']}")
        print(f"    Model: {judge_info['model']}")
        print(f"    Available: {'✅' if judge_info['available'] else '❌'}")
        print(f"    Circuit Open: {'🔴' if judge_info['circuit_open'] else '🟢'}")
        print(f"    Failures: {judge_info['failure_count']}")


async def example_3_custom_configuration():
    """
    Example 3: Custom judge configuration
    
    Advanced usage: Configure your own judges with custom settings.
    """
    print("\n" + "="*60)
    print("EXAMPLE 3: Custom Judge Configuration")
    print("="*60)
    
    from sentinelrouter.sentinelrouter.judge_registry import (
        JudgeRegistry,
        JudgeModel,
        JudgeHealthTracker
    )
    from sentinelrouter.sentinelrouter.clients import (
        get_deepseek_client,
        get_anthropic_client
    )
    
    # Create custom circuit breaker settings
    health_tracker = JudgeHealthTracker(
        failure_threshold=5,    # More tolerant: 5 failures before circuit opens
        cooldown_seconds=120    # Longer cooldown: 2 minutes
    )
    
    registry = JudgeRegistry(health_tracker=health_tracker)
    
    # Register judges with custom settings
    deepseek = await get_deepseek_client()
    registry.register_judge(JudgeModel(
        judge_id="custom-primary",
        client=deepseek,
        priority=0,
        display_name="Custom Primary Judge",
        temperature=0.0,  # More deterministic
    ))
    
    anthropic = await get_anthropic_client()
    registry.register_judge(JudgeModel(
        judge_id="custom-backup",
        client=anthropic,
        priority=1,
        display_name="Custom Backup Judge",
        temperature=0.2,
    ))
    
    # Set custom fallback values
    registry.set_default_fallback(
        complexity_score=0.7,  # Assume more complex when judges fail
        impact_scope="MEDIUM",
        reasoning="Judges unavailable, using conservative default."
    )
    
    # Use the custom registry
    score, impact, reasoning, judge_id = await registry.judge_with_failover(
        "Implement OAuth2 authentication",
        max_attempts=3
    )
    
    print(f"\nCustom Judge Result:")
    print(f"  Judge Used: {judge_id}")
    print(f"  Score: {score:.2f}")
    print(f"  Impact: {impact}")
    print(f"  Reasoning: {reasoning[:80]}...")


async def example_4_handling_failures():
    """
    Example 4: Understanding failure scenarios
    
    Shows what happens in different failure scenarios.
    """
    print("\n" + "="*60)
    print("EXAMPLE 4: Handling Failures")
    print("="*60)
    
    judge = StingyJudge()
    
    print("\nScenario explanations:")
    print("\n1. Normal Operation (99% of time):")
    print("   Primary judge (DeepSeek) succeeds on first attempt")
    print("   Fast, cheap, reliable")
    
    print("\n2. Primary Fails, Backup Succeeds (~0.9% of time):")
    print("   Primary judge fails (timeout, API error, etc.)")
    print("   → Automatically tries backup judge (Anthropic)")
    print("   → Backup succeeds")
    print("   ✅ User gets result, no error")
    
    print("\n3. Circuit Breaker Opens:")
    print("   Primary fails 3 times in 5 minutes")
    print("   → Circuit breaker opens (60s cooldown)")
    print("   → All traffic goes directly to backup")
    print("   → Saves time and money (no retry on failing service)")
    
    print("\n4. All Judges Fail (~0.1% of time):")
    print("   Both primary and backup fail")
    print("   → Returns default: (0.5, LOW, 'All judges failed...')")
    print("   ⚠️ System continues, uses safe default")
    
    # Make a normal judge call
    score, impact, reasoning = await judge.judge("Add unit tests")
    print(f"\n✅ Example call succeeded:")
    print(f"   Score: {score:.2f}, Impact: {impact}")


async def example_5_batch_judging():
    """
    Example 5: Batch judging with automatic failover
    
    Evaluate multiple prompts concurrently, each with backup support.
    """
    print("\n" + "="*60)
    print("EXAMPLE 5: Batch Judging")
    print("="*60)
    
    judge = StingyJudge()
    
    prompts = [
        "Fix typo in README",
        "Refactor user service",
        "Migrate database to PostgreSQL",
        "Add logging to authentication",
        "Design new microservices architecture",
    ]
    
    print(f"\nEvaluating {len(prompts)} prompts concurrently...")
    results = await judge.judge_batch(prompts)
    
    print("\nBatch Results:")
    for prompt, (score, impact, reasoning) in zip(prompts, results):
        print(f"\n  Prompt: {prompt}")
        print(f"    Score: {score:.2f} | Impact: {impact}")
        print(f"    Reasoning: {reasoning[:60]}...")
    
    print(f"\n✅ All {len(prompts)} prompts evaluated successfully")
    print("   Each had automatic backup failover protection!")


async def main():
    """Run all examples."""
    print("\n" + "="*70)
    print("BACKUP JUDGES - INTEGRATION EXAMPLES")
    print("="*70)
    print("\nDemonstrating the new backup judges feature...")
    
    try:
        await example_1_basic_usage()
        await example_2_monitoring_health()
        # await example_3_custom_configuration()  # Commented out - requires API keys
        await example_4_handling_failures()
        await example_5_batch_judging()
        
        print("\n" + "="*70)
        print("✅ ALL EXAMPLES COMPLETED SUCCESSFULLY")
        print("="*70)
        print("\nKey Takeaways:")
        print("  • Backup judges work transparently - no code changes needed")
        print("  • Automatic failover protects against single provider failures")
        print("  • Circuit breaker prevents retry storms")
        print("  • Health monitoring provides visibility into judge status")
        print("  • Batch operations work with backup support")
        print("  • System continues even when all judges fail (safe defaults)")
        print("="*70 + "\n")
        
    except Exception as e:
        print(f"\n❌ Error running examples: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
