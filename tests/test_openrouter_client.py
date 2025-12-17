"""Unit tests for OpenRouter client."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from sentinelrouter.sentinelrouter.clients import OpenRouterClient, LLMResponse, LLMClientError


class TestOpenRouterClient:
    """Test suite for OpenRouter client."""
    
    @patch('sentinelrouter.sentinelrouter.clients.get_settings')
    def test_client_initialization_with_key(self, mock_get_settings):
        """Test client initializes correctly with API key."""
        mock_settings = Mock()
        mock_settings.openrouter_api_key = "test-key"
        mock_settings.openrouter_http_referer = "http://localhost"
        mock_settings.openrouter_app_title = "TestApp"
        mock_get_settings.return_value = mock_settings
        
        client = OpenRouterClient(model_key="meta-llama/llama-3.2-3b-instruct:free")
        assert client.api_key == "test-key"
        assert client.base_url == "https://openrouter.ai/api/v1"
        assert client.model_key == "meta-llama/llama-3.2-3b-instruct:free"
        assert client.is_available() is True
    
    @patch('sentinelrouter.sentinelrouter.clients.get_settings')
    def test_client_initialization_without_key(self, mock_get_settings):
        """Test client handles missing API key gracefully."""
        mock_settings = Mock()
        mock_settings.openrouter_api_key = None
        mock_settings.openrouter_http_referer = "http://localhost"
        mock_settings.openrouter_app_title = "TestApp"
        mock_get_settings.return_value = mock_settings
        
        client = OpenRouterClient(model_key="meta-llama/llama-3.2-3b-instruct:free")
        assert client.api_key is None
        assert client.is_available() is False
    
    @pytest.mark.asyncio
    @patch('sentinelrouter.sentinelrouter.clients.get_settings')
    async def test_chat_completion_success(self, mock_get_settings):
        """Test successful chat completion request."""
        mock_settings = Mock()
        mock_settings.openrouter_api_key = "test-key"
        mock_settings.openrouter_http_referer = "http://localhost"
        mock_settings.openrouter_app_title = "TestApp"
        mock_get_settings.return_value = mock_settings
        
        client = OpenRouterClient(model_key="meta-llama/llama-3.2-3b-instruct:free")
        
        # Mock the HTTP client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "Test response content"
                }
            }],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30
            }
        }
        
        # Mock raise_for_status to do nothing
        mock_response.raise_for_status = Mock()
        
        # Create async mock for post
        async_mock_post = AsyncMock(return_value=mock_response)
        client.client.post = async_mock_post
        
        # Make request
        response = await client.chat_completion(
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.7
        )
        
        # Verify request was made correctly
        async_mock_post.assert_called_once()
        call_args = async_mock_post.call_args
        
        # Check URL
        assert call_args[0][0] == "https://openrouter.ai/api/v1/chat/completions"
        
        # Check headers
        headers = call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer test-key"
        assert "HTTP-Referer" in headers
        assert "X-Title" in headers
        
        # Check request body
        json_data = call_args[1]["json"]
        assert json_data["model"] == "meta-llama/llama-3.2-3b-instruct:free"
        assert json_data["messages"] == [{"role": "user", "content": "Hello"}]
        assert json_data["temperature"] == 0.7
        
        # Verify response
        assert isinstance(response, LLMResponse)
        assert response.content == "Test response content"
        assert response.usage["prompt_tokens"] == 10
        assert response.usage["completion_tokens"] == 20
        assert response.usage["total_tokens"] == 30
        assert response.cost == 0.0  # Free tier
    
    @pytest.mark.asyncio
    @patch('sentinelrouter.sentinelrouter.clients.get_settings')
    async def test_chat_completion_api_error(self, mock_get_settings):
        """Test handling of API error responses."""
        mock_settings = Mock()
        mock_settings.openrouter_api_key = "test-key"
        mock_settings.openrouter_http_referer = "http://localhost"
        mock_settings.openrouter_app_title = "TestApp"
        mock_get_settings.return_value = mock_settings

        client = OpenRouterClient(model_key="meta-llama/llama-3.2-3b-instruct:free")
        
        # Mock API error response (non-retriable error)
        import httpx
        mock_response = Mock()
        mock_response.status_code = 400  # Use 400 instead of 429 to avoid retries
        mock_response.text = "Bad request"

        def raise_http_error():
            raise httpx.HTTPStatusError("Bad request", request=Mock(), response=mock_response)
        
        mock_response.raise_for_status = raise_http_error

        async_mock_post = AsyncMock(return_value=mock_response)
        client.client.post = async_mock_post

        # Request should raise exception immediately (no retries for 400)
        with pytest.raises(LLMClientError, match="OpenRouter HTTP error"):
            await client.chat_completion(
                messages=[{"role": "user", "content": "Hello"}]
            )    @pytest.mark.asyncio
    @patch('sentinelrouter.sentinelrouter.clients.get_settings')
    async def test_chat_completion_without_api_key(self, mock_get_settings):
        """Test that request fails gracefully without API key."""
        mock_settings = Mock()
        mock_settings.openrouter_api_key = None
        mock_settings.openrouter_http_referer = "http://localhost"
        mock_settings.openrouter_app_title = "TestApp"
        mock_get_settings.return_value = mock_settings
        
        client = OpenRouterClient(model_key="meta-llama/llama-3.2-3b-instruct:free")
        
        with pytest.raises(LLMClientError, match="OpenRouter API key not configured"):
            await client.chat_completion(
                messages=[{"role": "user", "content": "Hello"}]
            )
    
    @pytest.mark.asyncio
    @patch('sentinelrouter.sentinelrouter.clients.get_settings')
    async def test_chat_completion_with_optional_params(self, mock_get_settings):
        """Test chat completion with optional parameters like tools."""
        mock_settings = Mock()
        mock_settings.openrouter_api_key = "test-key"
        mock_settings.openrouter_http_referer = "http://localhost"
        mock_settings.openrouter_app_title = "TestApp"
        mock_get_settings.return_value = mock_settings
        
        client = OpenRouterClient(model_key="meta-llama/llama-3.2-3b-instruct:free")
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Response"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        }
        mock_response.raise_for_status = Mock()
        
        async_mock_post = AsyncMock(return_value=mock_response)
        client.client.post = async_mock_post
        
        tools = [{"type": "function", "function": {"name": "test"}}]
        
        await client.chat_completion(
            messages=[{"role": "user", "content": "Hello"}],
            tools=tools,
            tool_choice="auto",
            max_tokens=100
        )
        
        # Verify optional parameters were included in request
        json_data = async_mock_post.call_args[1]["json"]
        assert json_data["tools"] == tools
        assert json_data["tool_choice"] == "auto"
        assert json_data["max_tokens"] == 100
    
    @pytest.mark.asyncio
    @patch('sentinelrouter.sentinelrouter.clients.get_settings')
    async def test_close(self, mock_get_settings):
        """Test client close method."""
        mock_settings = Mock()
        mock_settings.openrouter_api_key = "test-key"
        mock_settings.openrouter_http_referer = "http://localhost"
        mock_settings.openrouter_app_title = "TestApp"
        mock_get_settings.return_value = mock_settings
        
        client = OpenRouterClient(model_key="meta-llama/llama-3.2-3b-instruct:free")
        client.client.aclose = AsyncMock()
        
        await client.close()
        client.client.aclose.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
