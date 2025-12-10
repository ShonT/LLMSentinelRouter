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
    def judge(self):
        """Create a StingyJudge instance."""
        return StingyJudge()
    
    @pytest.mark.asyncio
    async def test_judge_simple_query(self, judge):
        """Test judging a simple query."""
        # Mock the DeepSeek client response
        mock_response = LLMResponse(
            content=json.dumps({
                "complexity_score": 0.2,
                "impact_scope": "LOW",
                "reasoning": "Simple factual question"
            }),
            model="deepseek-chat",
            usage={"total_tokens": 50},
            cost=0.0001
        )
        
        with patch("sentinelrouter.sentinelrouter.judge.get_deepseek_client") as mock_client:
            mock_client.return_value.chat_completion = AsyncMock(return_value=mock_response)
            
            score, impact, reasoning = await judge.judge("What is 2 + 2?")
            
            assert score == 0.2
            assert impact == "LOW"
            assert "Simple" in reasoning or "factual" in reasoning.lower()
    
    @pytest.mark.asyncio
    async def test_judge_complex_query(self, judge):
        """Test judging a complex query."""
        mock_response = LLMResponse(
            content=json.dumps({
                "complexity_score": 0.9,
                "impact_scope": "HIGH",
                "reasoning": "Requires deep analysis and reasoning"
            }),
            model="deepseek-chat",
            usage={"total_tokens": 100},
            cost=0.0002
        )
        
        with patch("sentinelrouter.sentinelrouter.judge.get_deepseek_client") as mock_client:
            mock_client.return_value.chat_completion = AsyncMock(return_value=mock_response)
            
            score, impact, reasoning = await judge.judge(
                "Explain the philosophical implications of quantum entanglement on free will"
            )
            
            assert score >= 0.8
            assert impact == "HIGH"
            assert len(reasoning) > 0
    
    @pytest.mark.asyncio
    async def test_judge_medium_complexity(self, judge):
        """Test judging a medium complexity query."""
        mock_response = LLMResponse(
            content=json.dumps({
                "complexity_score": 0.6,
                "impact_scope": "MEDIUM",
                "reasoning": "Requires some domain knowledge"
            }),
            model="deepseek-chat",
            usage={"total_tokens": 75},
            cost=0.00015
        )
        
        with patch("sentinelrouter.sentinelrouter.judge.get_deepseek_client") as mock_client:
            mock_client.return_value.chat_completion = AsyncMock(return_value=mock_response)
            
            score, impact, reasoning = await judge.judge(
                "Explain how neural networks learn from data"
            )
            
            assert 0.5 <= score <= 0.7
            assert impact == "MEDIUM"
    
    @pytest.mark.asyncio
    async def test_judge_fallback_on_error(self, judge):
        """Test that judge falls back to safe defaults on error."""
        with patch("sentinelrouter.sentinelrouter.judge.get_deepseek_client") as mock_client:
            mock_client.return_value.chat_completion = AsyncMock(
                side_effect=Exception("API error")
            )
            
            score, impact, reasoning = await judge.judge("Test prompt")
            
            # Should return safe defaults
            assert score == 0.5
            assert impact == "LOW"
            assert "Judge failed" in reasoning
    
    @pytest.mark.asyncio
    async def test_judge_malformed_json(self, judge):
        """Test handling of malformed JSON response."""
        mock_response = LLMResponse(
            content="This is not valid JSON",
            model="deepseek-chat",
            usage={"total_tokens": 50},
            cost=0.0001
        )
        
        with patch("sentinelrouter.sentinelrouter.judge.get_deepseek_client") as mock_client:
            mock_client.return_value.chat_completion = AsyncMock(return_value=mock_response)
            
            score, impact, reasoning = await judge.judge("Test prompt")
            
            # Should return safe defaults
            assert score == 0.5
            assert impact == "LOW"
            assert "Judge failed" in reasoning
    
    @pytest.mark.asyncio
    async def test_judge_missing_fields(self, judge):
        """Test handling of JSON with missing fields."""
        mock_response = LLMResponse(
            content=json.dumps({
                "complexity_score": 0.7
                # Missing impact_scope and reasoning
            }),
            model="deepseek-chat",
            usage={"total_tokens": 50},
            cost=0.0001
        )
        
        with patch("sentinelrouter.sentinelrouter.judge.get_deepseek_client") as mock_client:
            mock_client.return_value.chat_completion = AsyncMock(return_value=mock_response)
            
            score, impact, reasoning = await judge.judge("Test prompt")
            
            # Should handle missing fields gracefully
            assert isinstance(score, float)
            assert impact in ["LOW", "MEDIUM", "HIGH"]
    
    @pytest.mark.asyncio
    async def test_judge_batch(self, judge):
        """Test judging multiple prompts in batch."""
        prompts = [
            "What is 1+1?",
            "Explain quantum mechanics",
            "What's the weather?"
        ]
        
        mock_responses = [
            LLMResponse(
                content=json.dumps({
                    "complexity_score": 0.1,
                    "impact_scope": "LOW",
                    "reasoning": "Simple math"
                }),
                model="deepseek-chat",
                usage={"total_tokens": 50},
                cost=0.0001
            ),
            LLMResponse(
                content=json.dumps({
                    "complexity_score": 0.9,
                    "impact_scope": "HIGH",
                    "reasoning": "Complex physics"
                }),
                model="deepseek-chat",
                usage={"total_tokens": 100},
                cost=0.0002
            ),
            LLMResponse(
                content=json.dumps({
                    "complexity_score": 0.3,
                    "impact_scope": "LOW",
                    "reasoning": "Simple query"
                }),
                model="deepseek-chat",
                usage={"total_tokens": 50},
                cost=0.0001
            )
        ]
        
        with patch("sentinelrouter.sentinelrouter.judge.get_deepseek_client") as mock_client:
            mock_client.return_value.chat_completion = AsyncMock(
                side_effect=mock_responses
            )
            
            results = await judge.judge_batch(prompts)
            
            assert len(results) == 3
            assert results[0][0] < 0.5  # First should be low complexity
            assert results[1][0] > 0.8  # Second should be high complexity
            assert results[2][0] < 0.5  # Third should be low complexity
    
    @pytest.mark.asyncio
    async def test_judge_score_bounds(self, judge):
        """Test that complexity scores are properly bounded."""
        # Test score above 1.0
        mock_response = LLMResponse(
            content=json.dumps({
                "complexity_score": 1.5,
                "impact_scope": "HIGH",
                "reasoning": "Very complex"
            }),
            model="deepseek-chat",
            usage={"total_tokens": 50},
            cost=0.0001
        )
        
        with patch("sentinelrouter.sentinelrouter.judge.get_deepseek_client") as mock_client:
            mock_client.return_value.chat_completion = AsyncMock(return_value=mock_response)
            
            score, impact, reasoning = await judge.judge("Test")
            
            # Score should be clamped to valid range
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
    async def test_judge_with_context(self, judge):
        """Test judge with additional context."""
        context = {
            "user_id": "test_user",
            "previous_queries": 5
        }
        
        mock_response = LLMResponse(
            content=json.dumps({
                "complexity_score": 0.4,
                "impact_scope": "LOW",
                "reasoning": "Simple with context"
            }),
            model="deepseek-chat",
            usage={"total_tokens": 50},
            cost=0.0001
        )
        
        with patch("sentinelrouter.sentinelrouter.judge.get_deepseek_client") as mock_client:
            mock_client.return_value.chat_completion = AsyncMock(return_value=mock_response)
            
            score, impact, reasoning = await judge.judge("Test", context=context)
            
            assert 0.0 <= score <= 1.0
            assert impact in ["LOW", "MEDIUM", "HIGH"]
    
    @pytest.mark.asyncio
    async def test_judge_empty_prompt(self, judge):
        """Test judge with empty prompt."""
        mock_response = LLMResponse(
            content=json.dumps({
                "complexity_score": 0.1,
                "impact_scope": "LOW",
                "reasoning": "Empty or minimal input"
            }),
            model="deepseek-chat",
            usage={"total_tokens": 30},
            cost=0.00005
        )
        
        with patch("sentinelrouter.sentinelrouter.judge.get_deepseek_client") as mock_client:
            mock_client.return_value.chat_completion = AsyncMock(return_value=mock_response)
            
            score, impact, reasoning = await judge.judge("")
            
            assert score >= 0.0
            assert impact in ["LOW", "MEDIUM", "HIGH"]
    
    @pytest.mark.asyncio
    async def test_judge_very_long_prompt(self, judge):
        """Test judge with very long prompt."""
        long_prompt = "What is the meaning of life? " * 1000
        
        mock_response = LLMResponse(
            content=json.dumps({
                "complexity_score": 0.7,
                "impact_scope": "MEDIUM",
                "reasoning": "Long philosophical query"
            }),
            model="deepseek-chat",
            usage={"total_tokens": 500},
            cost=0.001
        )
        
        with patch("sentinelrouter.sentinelrouter.judge.get_deepseek_client") as mock_client:
            mock_client.return_value.chat_completion = AsyncMock(return_value=mock_response)
            
            score, impact, reasoning = await judge.judge(long_prompt)
            
            assert 0.0 <= score <= 1.0
            assert impact in ["LOW", "MEDIUM", "HIGH"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
