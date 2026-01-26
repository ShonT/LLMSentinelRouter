"""
Tests for Groq client implementation.
"""

import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from sentinelrouter.sentinelrouter.clients import GroqClient, LLMClientError


@pytest.fixture
def groq_client():
    """Create a Groq client for testing."""
    with patch("sentinelrouter.sentinelrouter.clients.get_settings") as mock_settings:
        settings = MagicMock()
        settings.groq_api_key = "test-groq-key"
        mock_settings.return_value = settings
        client = GroqClient(model_key="llama3-8b-8192")
        yield client


@pytest.mark.asyncio
async def test_groq_client_initialization():
    """Test Groq client initialization."""
    with patch("sentinelrouter.sentinelrouter.clients.get_settings") as mock_settings:
        settings = MagicMock()
        settings.groq_api_key = "test-groq-key"
        mock_settings.return_value = settings

        client = GroqClient(model_key="llama3-8b-8192")

        assert client.model_key == "llama3-8b-8192"
        assert client.base_url == "https://api.groq.com/openai/v1"
        assert client.api_key == "test-groq-key"
        assert client.max_retries == 1  # Limited retries for quota-based service
        assert client.is_available() is True


@pytest.mark.asyncio
async def test_groq_client_unavailable_without_api_key():
    """Test that Groq client is unavailable when API key is missing."""
    with patch("sentinelrouter.sentinelrouter.clients.get_settings") as mock_settings:
        settings = MagicMock()
        settings.groq_api_key = None
        mock_settings.return_value = settings

        client = GroqClient(model_key="llama3-8b-8192")

        assert client.is_available() is False


@pytest.mark.asyncio
async def test_groq_chat_completion_success(groq_client):
    """Test successful chat completion with Groq."""
    mock_response = {
        "choices": [{"message": {"content": "Hello! I'm a test response from Groq."}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 15, "total_tokens": 25},
    }

    with patch.object(groq_client.client, "post", new_callable=AsyncMock) as mock_post:
        mock_http_response = MagicMock()
        mock_http_response.json.return_value = mock_response
        mock_http_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_http_response

        messages = [{"role": "user", "content": "Hello"}]

        response = await groq_client.chat_completion(messages, temperature=0.7)

        # Verify request was made correctly
        mock_post.assert_called_once()
        call_args = mock_post.call_args

        # Check URL
        assert call_args[0][0] == "https://api.groq.com/openai/v1/chat/completions"

        # Check headers
        headers = call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer test-groq-key"
        assert headers["Content-Type"] == "application/json"

        # Check payload
        payload = call_args[1]["json"]
        assert payload["model"] == "llama3-8b-8192"
        assert payload["messages"] == messages
        assert payload["temperature"] == 0.7

        # Verify response
        assert response.content == "Hello! I'm a test response from Groq."
        assert response.model == "llama3-8b-8192"
        assert response.usage["total_tokens"] == 25
        assert response.cost == 0.0  # Quota-based, zero cost


@pytest.mark.asyncio
async def test_groq_chat_completion_no_api_key():
    """Test that chat completion fails when API key is not configured."""
    with patch("sentinelrouter.sentinelrouter.clients.get_settings") as mock_settings:
        settings = MagicMock()
        settings.groq_api_key = None
        mock_settings.return_value = settings

        client = GroqClient(model_key="llama3-8b-8192")

        messages = [{"role": "user", "content": "Hello"}]

        with pytest.raises(LLMClientError, match="Groq API key not configured"):
            await client.chat_completion(messages)


@pytest.mark.asyncio
async def test_groq_rate_limit_429(groq_client):
    """Test that 429 rate limit errors are handled correctly without aggressive retry."""
    with patch.object(groq_client.client, "post", new_callable=AsyncMock) as mock_post:
        # Mock a 429 response
        mock_http_response = MagicMock()
        mock_http_response.status_code = 429
        mock_http_response.text = "Rate limit exceeded"

        def raise_429(*args, **kwargs):
            raise httpx.HTTPStatusError(
                "Rate limited", request=MagicMock(), response=mock_http_response
            )

        mock_http_response.raise_for_status = raise_429
        mock_post.return_value = mock_http_response

        messages = [{"role": "user", "content": "Hello"}]

        # Should raise LLMClientError and NOT retry
        with pytest.raises(LLMClientError, match="Groq rate limited"):
            await groq_client.chat_completion(messages)

        # Should only be called once (no retries for 429)
        assert mock_post.call_count == 1


@pytest.mark.asyncio
async def test_groq_service_unavailable_503(groq_client):
    """Test that 503 service unavailable errors are handled correctly."""
    with patch.object(groq_client.client, "post", new_callable=AsyncMock) as mock_post:
        # Mock a 503 response
        mock_http_response = MagicMock()
        mock_http_response.status_code = 503
        mock_http_response.text = "Service unavailable"

        def raise_503(*args, **kwargs):
            raise httpx.HTTPStatusError(
                "Service unavailable", request=MagicMock(), response=mock_http_response
            )

        mock_http_response.raise_for_status = raise_503
        mock_post.return_value = mock_http_response

        messages = [{"role": "user", "content": "Hello"}]

        with pytest.raises(LLMClientError, match="Groq service unavailable"):
            await groq_client.chat_completion(messages)


@pytest.mark.asyncio
async def test_groq_http_error_other(groq_client):
    """Test that other HTTP errors are handled correctly."""
    with patch.object(groq_client.client, "post", new_callable=AsyncMock) as mock_post:
        # Mock a 400 response
        mock_http_response = MagicMock()
        mock_http_response.status_code = 400
        mock_http_response.text = "Bad request"

        def raise_400(*args, **kwargs):
            raise httpx.HTTPStatusError(
                "Bad request", request=MagicMock(), response=mock_http_response
            )

        mock_http_response.raise_for_status = raise_400
        mock_post.return_value = mock_http_response

        messages = [{"role": "user", "content": "Hello"}]

        with pytest.raises(LLMClientError, match="Groq HTTP error 400"):
            await groq_client.chat_completion(messages)


@pytest.mark.asyncio
async def test_groq_request_error(groq_client):
    """Test that network request errors are handled correctly."""
    with patch.object(groq_client.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.RequestError("Connection failed")

        messages = [{"role": "user", "content": "Hello"}]

        with pytest.raises(LLMClientError, match="Groq request error"):
            await groq_client.chat_completion(messages)


@pytest.mark.asyncio
async def test_groq_client_close(groq_client):
    """Test that client properly closes HTTP connections."""
    with patch.object(
        groq_client.client, "aclose", new_callable=AsyncMock
    ) as mock_close:
        await groq_client.close()
        mock_close.assert_called_once()


@pytest.mark.asyncio
async def test_groq_openai_compatible_format(groq_client):
    """Test that Groq uses OpenAI-compatible request/response format."""
    mock_response = {
        "choices": [{"message": {"content": "Test response"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
    }

    with patch.object(groq_client.client, "post", new_callable=AsyncMock) as mock_post:
        mock_http_response = MagicMock()
        mock_http_response.json.return_value = mock_response
        mock_http_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_http_response

        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
        ]

        response = await groq_client.chat_completion(
            messages, temperature=0.5, max_tokens=100
        )

        # Verify payload matches OpenAI format
        payload = mock_post.call_args[1]["json"]
        assert "model" in payload
        assert "messages" in payload
        assert payload["messages"] == messages
        assert payload["temperature"] == 0.5
        assert payload["max_tokens"] == 100

        # Verify response extraction
        assert response.content == "Test response"
        assert response.usage["prompt_tokens"] == 5
        assert response.usage["completion_tokens"] == 2
