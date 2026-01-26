"""
Simplified unit tests for LLM Clients
Tests basic functionality without complex mocking.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sentinelrouter.sentinelrouter.clients import (
    LLMResponse,
    LLMClientError,
    get_deepseek_client,
    get_anthropic_client,
    close_clients,
)


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_llm_response_creation(self):
        """Test creating an LLMResponse."""
        response = LLMResponse(
            content="Test response",
            model="test-model",
            usage={"total_tokens": 100},
            cost=0.001,
        )

        assert response.content == "Test response"
        assert response.model == "test-model"
        assert response.usage["total_tokens"] == 100
        assert response.cost == 0.001

    def test_llm_response_optional_fields(self):
        """Test LLMResponse with optional fields."""
        response = LLMResponse(content="Test", model="model", usage=None, cost=0.0)

        assert response.usage is None
        assert response.cost == 0.0


class TestLLMClientError:
    """Tests for LLMClientError exception."""

    def test_client_error_creation(self):
        """Test creating an LLMClientError."""
        error = LLMClientError("Test error")
        assert str(error) == "Test error"

    def test_client_error_raise(self):
        """Test raising an LLMClientError."""
        with pytest.raises(LLMClientError) as exc_info:
            raise LLMClientError("Custom error message")

        assert "Custom error message" in str(exc_info.value)


class TestClientSingletons:
    """Tests for client singleton pattern."""

    @pytest.mark.asyncio
    async def test_get_deepseek_client_singleton(self):
        """Test that get_deepseek_client returns singleton."""
        # Clean up first
        await close_clients()

        client1 = await get_deepseek_client()
        client2 = await get_deepseek_client()

        assert client1 is client2
        assert client1 is not None

    @pytest.mark.asyncio
    async def test_get_anthropic_client_singleton(self):
        """Test that get_anthropic_client returns singleton."""
        # Clean up first
        await close_clients()

        client1 = await get_anthropic_client()
        client2 = await get_anthropic_client()

        assert client1 is client2
        assert client1 is not None

    @pytest.mark.asyncio
    async def test_close_clients(self):
        """Test closing all clients."""
        # Get clients
        deepseek = await get_deepseek_client()
        anthropic = await get_anthropic_client()

        assert deepseek is not None
        assert anthropic is not None

        # Close them
        await close_clients()

        # Should be able to get new instances
        new_deepseek = await get_deepseek_client()
        new_anthropic = await get_anthropic_client()

        assert new_deepseek is not None
        assert new_anthropic is not None
        # After close, new instances are created
        assert new_deepseek is not deepseek  # Different instance after close
        assert new_anthropic is not anthropic


class TestDeepSeekClient:
    """Tests for DeepSeek client properties and structure."""

    @pytest.mark.asyncio
    async def test_client_initialization(self):
        """Test that DeepSeek client initializes correctly."""
        await close_clients()
        client = await get_deepseek_client()

        assert client.model_id is not None
        assert client.price_per_token > 0
        assert client.base_url == "https://api.deepseek.com"
        assert hasattr(client, "chat_completion")

    @pytest.mark.asyncio
    async def test_client_has_required_methods(self):
        """Test that client has required methods."""
        client = await get_deepseek_client()

        assert callable(getattr(client, "chat_completion", None))
        assert callable(getattr(client, "close", None))


class TestAnthropicClient:
    """Tests for Anthropic client properties and structure."""

    @pytest.mark.asyncio
    async def test_client_initialization(self):
        """Test that Anthropic client initializes correctly."""
        await close_clients()
        client = await get_anthropic_client()

        assert client.model_id is not None
        assert client.price_per_token > 0
        assert client.base_url == "https://api.anthropic.com"
        assert hasattr(client, "chat_completion")

    @pytest.mark.asyncio
    async def test_client_has_required_methods(self):
        """Test that client has required methods."""
        client = await get_anthropic_client()

        assert callable(getattr(client, "chat_completion", None))
        assert callable(getattr(client, "close", None))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
