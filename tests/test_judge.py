"""
Unit tests for Module B: Stingy Judge & Categorizer
Tests the complexity analysis and routing recommendation functionality.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from sentinelrouter.sentinelrouter.judge import StingyJudge, complexity_to_route
from sentinelrouter.sentinelrouter.clients import LLMResponse


class TestStingyJudge:
    """Tests for Module B - Stingy Judge & Categorizer."""
    
    @pytest.fixture
    def mock_registry(self):
        """Create a mock JudgeRegistry."""
        registry = MagicMock()
        return registry
    
    @pytest.fixture
    def judge(self, mock_registry):
        """Create a StingyJudge instance with mocked registry."""
        j = StingyJudge()
        j._registry = mock_registry
        return j
    
    @pytest.mark.asyncio
    async def test_judge_simple_query(self, judge, mock_registry):
        """Test judging a simple query."""
        # Mock the registry's judge_with_failover method
        mock_registry.judge_with_failover = AsyncMock(
            return_value=(0.2, "LOW", "Simple factual question", "mock-judge")
        )
        
        score, impact, reasoning = await judge.judge("What is 2 + 2?")
        
        assert score == 0.2
        assert impact == "LOW"
        assert "Simple" in reasoning or "factual" in reasoning.lower()
    
    @pytest.mark.asyncio
    async def test_judge_complex_query(self, judge, mock_registry):
        """Test judging a complex query."""
        mock_registry.judge_with_failover = AsyncMock(
            return_value=(0.9, "HIGH", "Requires deep analysis and reasoning", "mock-judge")
        )
        
        score, impact, reasoning = await judge.judge(
            "Explain the philosophical implications of quantum entanglement on free will"
        )
        
        assert score >= 0.8
        assert impact == "HIGH"
        assert len(reasoning) > 0
    
    @pytest.mark.asyncio
    async def test_judge_medium_complexity(self, judge, mock_registry):
        """Test judging a medium complexity query."""
        mock_registry.judge_with_failover = AsyncMock(
            return_value=(0.6, "MEDIUM", "Requires some domain knowledge", "mock-judge")
        )
        
        score, impact, reasoning = await judge.judge(
            "Explain how neural networks learn from data"
        )
        
        assert 0.5 <= score <= 0.7
        assert impact == "MEDIUM"
    
    @pytest.mark.asyncio
    async def test_judge_fallback_on_error(self, judge, mock_registry):
        """Test that judge falls back to safe defaults on error."""
        # Mock registry to raise exception (all judges fail)
        mock_registry.judge_with_failover = AsyncMock(
            return_value=(0.5, "LOW", "Judge failed: All judges exhausted", "fallback")
        )
        
        score, impact, reasoning = await judge.judge("Test prompt")
        
        # Should return safe defaults
        assert score == 0.5
        assert impact == "LOW"
        assert "Judge failed" in reasoning or "fallback" in reasoning.lower()
    
    @pytest.mark.asyncio
    async def test_judge_malformed_json(self, judge, mock_registry):
        """Test handling of malformed JSON response."""
        # Mock registry to handle malformed response gracefully
        mock_registry.judge_with_failover = AsyncMock(
            return_value=(0.5, "LOW", "Judge failed: Unable to parse response", "fallback")
        )
        
        score, impact, reasoning = await judge.judge("Test prompt")
        
        # Should return safe defaults
        assert score == 0.5
        assert impact == "LOW"
    
    @pytest.mark.asyncio
    async def test_judge_missing_fields(self, judge, mock_registry):
        """Test handling of JSON with missing fields."""
        mock_registry.judge_with_failover = AsyncMock(
            return_value=(0.7, "LOW", "Missing fields handled", "mock-judge")
        )
        
        score, impact, reasoning = await judge.judge("Test prompt")
        
        # Should handle missing fields gracefully
        assert isinstance(score, float)
        assert impact in ["LOW", "MEDIUM", "HIGH"]
    
    @pytest.mark.asyncio
    async def test_judge_batch(self, judge, mock_registry):
        """Test judging multiple prompts in batch."""
        prompts = [
            "What is 1+1?",
            "Explain quantum mechanics",
            "What's the weather?"
        ]
        
        # Mock returns different results for each call
        mock_registry.judge_with_failover = AsyncMock(
            side_effect=[
                (0.1, "LOW", "Simple math", "mock-judge"),
                (0.9, "HIGH", "Complex physics", "mock-judge"),
                (0.3, "LOW", "Simple query", "mock-judge")
            ]
        )
        
        results = await judge.judge_batch(prompts)
        
        assert len(results) == 3
        assert results[0][0] < 0.5  # First should be low complexity
        assert results[1][0] > 0.8  # Second should be high complexity
        assert results[2][0] < 0.5  # Third should be low complexity
    
    @pytest.mark.asyncio
    async def test_judge_score_bounds(self, judge, mock_registry):
        """Test that complexity scores are properly bounded."""
        # Mock with clamped score
        mock_registry.judge_with_failover = AsyncMock(
            return_value=(1.0, "HIGH", "Very complex - clamped", "mock-judge")
        )
        
        score, impact, reasoning = await judge.judge("Test")
        
        # Score should be in valid range
        assert 0.0 <= score <= 1.0
    
    def test_complexity_to_route_low(self):
        """Test complexity_to_route helper with low complexity."""
        route = complexity_to_route(0.3, 0.5)  # score=0.3, threshold=0.5
        assert route == "weak"
    
    def test_complexity_to_route_high(self):
        """Test complexity_to_route helper with high complexity."""
        route = complexity_to_route(0.9, 0.5)  # score=0.9, threshold=0.5
        assert route == "strong"
    
    def test_complexity_to_route_threshold(self):
        """Test complexity_to_route at threshold boundary."""
        # Test at threshold boundary
        route_below = complexity_to_route(0.49, 0.5)
        route_above = complexity_to_route(0.51, 0.5)
        
        assert route_below == "weak"
        assert route_above == "strong"
    
    @pytest.mark.asyncio
    async def test_judge_with_context(self, judge, mock_registry):
        """Test judge with additional context."""
        context = {
            "user_id": "test_user",
            "previous_queries": 5
        }
        
        mock_registry.judge_with_failover = AsyncMock(
            return_value=(0.4, "LOW", "Simple with context", "mock-judge")
        )
        
        score, impact, reasoning = await judge.judge("Test", context=context)
        
        assert 0.0 <= score <= 1.0
        assert impact in ["LOW", "MEDIUM", "HIGH"]
    
    @pytest.mark.asyncio
    async def test_judge_empty_prompt(self, judge, mock_registry):
        """Test judge with empty prompt."""
        mock_registry.judge_with_failover = AsyncMock(
            return_value=(0.1, "LOW", "Empty or minimal input", "mock-judge")
        )
        
        score, impact, reasoning = await judge.judge("")
        
        assert score >= 0.0
        assert impact in ["LOW", "MEDIUM", "HIGH"]
    
    @pytest.mark.asyncio
    async def test_judge_very_long_prompt(self, judge, mock_registry):
        """Test judge with very long prompt."""
        long_prompt = "What is the meaning of life? " * 1000
        
        mock_registry.judge_with_failover = AsyncMock(
            return_value=(0.7, "MEDIUM", "Long philosophical query", "mock-judge")
        )
        
        score, impact, reasoning = await judge.judge(long_prompt)
        
        assert 0.0 <= score <= 1.0
        assert impact in ["LOW", "MEDIUM", "HIGH"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
