"""
Unit tests for the router logic.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.orm import Session

from sentinelrouter.sentinelrouter.router_logic import Router
from sentinelrouter.sentinelrouter.budget import BudgetKillSwitch
from sentinelrouter.sentinelrouter.judge import StingyJudge
from sentinelrouter.sentinelrouter.threshold import DynamicThreshold
from sentinelrouter.sentinelrouter.clients import LLMResponse


@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)


@pytest.fixture
def router(mock_db):
    return Router(mock_db)


@pytest.mark.asyncio
async def test_router_initialization(router):
    """Test that Router initializes its components."""
    assert isinstance(router.budget, BudgetKillSwitch)
    assert isinstance(router.judge, StingyJudge)
    assert isinstance(router.threshold, DynamicThreshold)
    assert router.db is not None


@pytest.mark.asyncio
async def test_route_budget_exceeded(router):
    """Test that router rejects requests when budget is exceeded."""
    # Mock budget.check_budget to return False
    router.budget.check_budget = MagicMock(return_value=False)

    with pytest.raises(ValueError, match="Budget exceeded"):
        await router.route(
            session_id="test_session",
            prompt="test prompt",
            messages=[{"role": "user", "content": "test prompt"}],
        )


@pytest.mark.asyncio
async def test_route_success_weak(router):
    """Test successful routing to weak model."""
    # Mock budget.check_budget to return True
    router.budget.check_budget = MagicMock(return_value=True)
    # Mock judge.judge to return low complexity (score, impact_scope, reasoning)
    router.judge.judge = AsyncMock(return_value=(0.3, "LOW", "Simple query"))
    # Mock client
    mock_response = LLMResponse(
        content="Test response",
        model="deepseek-chat",
        usage={"total_tokens": 10},
        cost=0.0001,
    )
    with patch("sentinelrouter.sentinelrouter.router_logic.get_deepseek_client") as mock_client:
        mock_client.return_value.chat_completion = AsyncMock(return_value=mock_response)
        # Mock audit logger
        router.audit.log_routing_decision = MagicMock()
        router.budget.add_cost = MagicMock()

        result = await router.route(
            session_id="test_session",
            prompt="test prompt",
            messages=[{"role": "user", "content": "test prompt"}],
        )

    assert result["model_used"] == "deepseek"
    assert result["complexity_score"] == 0.3
    assert result["cost"] == 0.0001
    router.audit.log_routing_decision.assert_called_once()
    router.budget.add_cost.assert_called_once_with("test_session", 0.0001)


@pytest.mark.asyncio
async def test_route_success_strong(router):
    """Test successful routing to strong model."""
    router.budget.check_budget = MagicMock(return_value=True)
    # Mock judge to return high complexity (score, impact_scope, reasoning)
    router.judge.judge = AsyncMock(return_value=(0.8, "HIGH", "Complex reasoning task"))
    mock_response = LLMResponse(
        content="Test response from Claude",
        model="claude-3-haiku-20240307",
        usage={"input_tokens": 5, "output_tokens": 10},
        cost=0.0015,
    )
    with patch("sentinelrouter.sentinelrouter.router_logic.get_anthropic_client") as mock_client:
        mock_client.return_value.chat_completion = AsyncMock(return_value=mock_response)
        router.audit.log_routing_decision = MagicMock()
        router.budget.add_cost = MagicMock()

        result = await router.route(
            session_id="test_session",
            prompt="complex prompt",
            messages=[{"role": "user", "content": "complex prompt"}],
        )

    assert result["model_used"] == "anthropic"
    assert result["complexity_score"] == 0.8
    assert result["cost"] == 0.0015


def test_threshold_adjustment():
    """Test that DynamicThreshold adjusts correctly."""
    threshold = DynamicThreshold(target_rate=0.05, window_size=5, initial_threshold=0.5)
    # Add decisions that exceed target (3 strong out of 5 = 60%)
    for _ in range(3):
        threshold.add_decision(True)
    for _ in range(2):
        threshold.add_decision(False)
    new_threshold = threshold.adjust_threshold()
    # Expect threshold to increase
    assert new_threshold is not None
    assert threshold.get_threshold() > 0.5


if __name__ == "__main__":
    pytest.main([__file__])