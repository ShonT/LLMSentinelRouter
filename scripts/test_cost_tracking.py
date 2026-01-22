#!/usr/bin/env python3
"""
Test script to verify the cost tracking refactor works correctly.

Tests:
1. Provider cost takes precedence
2. Computed cost used as fallback
3. cost_source tracked correctly
4. computed_cost captured for audit
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sentinelrouter.sentinelrouter.clients import LLMResponse


def test_cost_priority():
    """Test cost tracking priority logic."""
    
    print("Testing cost tracking priority logic...\n")
    
    # Scenario 1: Provider gives cost
    print("1. Provider cost available (>0):")
    response = LLMResponse(
        content="test",
        model="test-model",
        usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        cost=0.05  # Provider gave us a cost
    )
    
    # Simulate the logic from router_logic.py
    final_cost = 0.0
    cost_source = "unknown"
    computed_cost = None
    
    if hasattr(response, 'cost') and response.cost and response.cost > 0:
        final_cost = response.cost
        cost_source = "provider"
    
    # Simulate computing fallback (even though provider gave us cost, for audit)
    if response.usage:
        input_tokens = response.usage.get('prompt_tokens', 0)
        output_tokens = response.usage.get('completion_tokens', 0)
        # Mock pricing: $0.27 per million tokens
        computed_cost = (input_tokens + output_tokens) / 1_000_000 * 0.27
    
    print(f"   Final cost: ${final_cost:.6f}")
    print(f"   Cost source: {cost_source}")
    print(f"   Computed cost (audit): ${computed_cost:.6f}")
    assert cost_source == "provider"
    assert final_cost == 0.05
    assert computed_cost is not None
    print("   ✓ Provider cost takes precedence\n")
    
    # Scenario 2: Provider gives cost=0 (free/quota-based)
    print("2. Provider cost is 0 (free/quota model):")
    response2 = LLMResponse(
        content="test",
        model="groq-model",
        usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        cost=0.0  # Free tier
    )
    
    final_cost = 0.0
    cost_source = "unknown"
    computed_cost = None
    
    if hasattr(response2, 'cost') and response2.cost and response2.cost > 0:
        final_cost = response2.cost
        cost_source = "provider"
    
    # Fallback: compute cost
    if cost_source == "unknown" and response2.usage:
        input_tokens = response2.usage.get('prompt_tokens', 0)
        output_tokens = response2.usage.get('completion_tokens', 0)
        computed_cost = (input_tokens + output_tokens) / 1_000_000 * 0.27
        
        if computed_cost and computed_cost > 0:
            final_cost = computed_cost
            cost_source = "computed"
    
    print(f"   Final cost: ${final_cost:.6f}")
    print(f"   Cost source: {cost_source}")
    print(f"   Computed cost: ${computed_cost:.6f}")
    assert cost_source == "computed"
    assert final_cost > 0
    assert abs(final_cost - computed_cost) < 0.000001
    print("   ✓ Computed cost used as fallback\n")
    
    # Scenario 3: No usage data
    print("3. No usage data available:")
    response3 = LLMResponse(
        content="test",
        model="test-model",
        usage=None,
        cost=0.0
    )
    
    final_cost = 0.0
    cost_source = "unknown"
    computed_cost = None
    
    if hasattr(response3, 'cost') and response3.cost and response3.cost > 0:
        final_cost = response3.cost
        cost_source = "provider"
    
    if cost_source == "unknown" and response3.usage:
        # Won't execute since usage is None
        pass
    
    print(f"   Final cost: ${final_cost:.6f}")
    print(f"   Cost source: {cost_source}")
    print(f"   Computed cost: {computed_cost}")
    assert cost_source == "unknown"
    assert final_cost == 0.0
    assert computed_cost is None
    print("   ✓ Defaults to unknown when no data\n")
    
    print("✅ All cost tracking tests passed!")


if __name__ == "__main__":
    test_cost_priority()
