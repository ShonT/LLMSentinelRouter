"""
Async HTTP clients for LLM providers (DeepSeek and Anthropic) with proper error handling and cost calculation.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional
import httpx
from pydantic import BaseModel

from .config import settings

logger = logging.getLogger(__name__)

# Hardcoded prices as per requirements (per million tokens)
DEEPSEEK_PRICE_PER_MILLION = 0.27      # $0.27 per million tokens
CLAUDE_OPUS_PRICE_PER_MILLION = 5.00   # $5.00 per million tokens (Claude Opus 4.5)
GEMINI_FLASH_PRICE_PER_MILLION = 0.10  # $0.10 per million tokens (Gemini Flash)

# Convert to per token
DEEPSEEK_PRICE_PER_TOKEN = DEEPSEEK_PRICE_PER_MILLION / 1_000_000
CLAUDE_OPUS_PRICE_PER_TOKEN = CLAUDE_OPUS_PRICE_PER_MILLION / 1_000_000
GEMINI_FLASH_PRICE_PER_TOKEN = GEMINI_FLASH_PRICE_PER_MILLION / 1_000_000


class LLMClientError(Exception):
    """Base exception for LLM client errors."""
    pass


class LLMResponse(BaseModel):
    """Standardized LLM response."""
    content: str
    model: str
    usage: Optional[Dict[str, Any]] = None  # Changed from int to Any to support nested dicts
    cost: float = 0.0


class BaseLLMClient:
    """Base class for LLM clients with retry and error handling."""

    def __init__(self, api_key: str, base_url: str, model_id: str, price_per_token: float, auth_header_type: str = "bearer"):
        self.api_key = api_key
        self.base_url = base_url
        self.model_id = model_id
        self.price_per_token = price_per_token
        self.auth_header_type = auth_header_type  # "bearer" or "x-api-key"
        self.client = httpx.AsyncClient(timeout=60.0)
        self.max_retries = 3

    async def close(self):
        """Close the underlying HTTP client."""
        await self.client.aclose()

    async def _request_with_retry(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Make an HTTP POST request with retry logic."""
        # Set auth header based on provider type
        if self.auth_header_type == "x-api-key":
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
        else:  # bearer token (default)
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        
        url = f"{self.base_url}{endpoint}"
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                logger.debug(f"Sending request to {url} (attempt {attempt+1}/{self.max_retries})")
                response = await self.client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                last_exception = e
                status = e.response.status_code
                if status in (429, 503):  # rate limit or service unavailable
                    wait = 2 ** attempt  # exponential backoff
                    logger.warning(f"Rate limited, waiting {wait}s...")
                    await asyncio.sleep(wait)
                    continue
                else:
                    logger.error(f"HTTP error from {url}: {status} - {e.response.text}")
                    raise LLMClientError(f"HTTP error {status}: {e.response.text}") from e
            except httpx.RequestError as e:
                last_exception = e
                logger.error(f"Request error from {url}: {e}")
                if attempt < self.max_retries - 1:
                    wait = 1.0 * (attempt + 1)
                    await asyncio.sleep(wait)
                    continue
                else:
                    raise LLMClientError(f"Request error after {self.max_retries} attempts: {e}") from e

        # If we exit the loop without returning, raise the last exception
        raise LLMClientError(f"Max retries exceeded for {url}") from last_exception

    async def chat_completion(self, messages: list, **kwargs) -> LLMResponse:
        """Abstract method to be implemented by subclasses."""
        raise NotImplementedError


class GeminiClient(BaseLLMClient):
    """Client for Google Gemini API (Flash 2.5 models)."""

    def __init__(self, api_key: str, model_id: str = "gemini-2.5-flash"):
        super().__init__(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta",
            model_id=model_id,
            price_per_token=GEMINI_FLASH_PRICE_PER_TOKEN,
            auth_header_type="api-key-param",  # Special handling for Gemini
        )

    async def chat_completion(self, messages: list, **kwargs) -> LLMResponse:
        """
        Get a chat completion from Gemini.
        Gemini uses a different API format than OpenAI/Anthropic.
        """
        # Convert OpenAI-style messages to Gemini format
        gemini_contents = []
        system_instruction = None
        
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            
            if role == "system":
                system_instruction = content
            elif role == "user":
                gemini_contents.append({"role": "user", "parts": [{"text": content}]})
            elif role == "assistant":
                gemini_contents.append({"role": "model", "parts": [{"text": content}]})
        
        # Build payload
        payload = {
            "contents": gemini_contents,
        }
        
        if system_instruction:
            payload["system_instruction"] = {"parts": [{"text": system_instruction}]}
        
        # Add generation config if provided
        generation_config = {}
        if "temperature" in kwargs:
            generation_config["temperature"] = kwargs["temperature"]
        if "response_format" in kwargs and kwargs["response_format"].get("type") == "json_object":
            generation_config["response_mime_type"] = "application/json"
        
        if generation_config:
            payload["generationConfig"] = generation_config
        
        # Gemini uses API key as query parameter, not header
        url = f"{self.base_url}/models/{self.model_id}:generateContent?key={self.api_key}"
        
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"Sending request to Gemini (attempt {attempt+1}/{self.max_retries})")
                headers = {"Content-Type": "application/json"}
                response = await self.client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                
                # Extract content from Gemini response
                if "candidates" not in data or not data["candidates"]:
                    raise LLMClientError("No candidates in Gemini response")
                
                candidate = data["candidates"][0]
                content_parts = candidate.get("content", {}).get("parts", [])
                
                if not content_parts:
                    raise LLMClientError("No content parts in Gemini response")
                
                content = content_parts[0].get("text", "")
                
                # Extract usage metadata
                usage_metadata = data.get("usageMetadata", {})
                prompt_tokens = usage_metadata.get("promptTokenCount", 0)
                completion_tokens = usage_metadata.get("candidatesTokenCount", 0)
                total_tokens = usage_metadata.get("totalTokenCount", prompt_tokens + completion_tokens)
                
                usage = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens
                }
                
                cost = total_tokens * self.price_per_token
                
                return LLMResponse(
                    content=content,
                    model=self.model_id,
                    usage=usage,
                    cost=cost,
                )
                
            except httpx.HTTPStatusError as e:
                last_exception = e
                status = e.response.status_code
                if status in (429, 503):
                    wait = 2 ** attempt
                    logger.warning(f"Gemini rate limited, waiting {wait}s...")
                    await asyncio.sleep(wait)
                    continue
                else:
                    logger.error(f"Gemini HTTP error: {status} - {e.response.text}")
                    raise LLMClientError(f"Gemini HTTP error {status}: {e.response.text}") from e
            except httpx.RequestError as e:
                last_exception = e
                logger.error(f"Gemini request error: {e}")
                if attempt < self.max_retries - 1:
                    wait = 1.0 * (attempt + 1)
                    await asyncio.sleep(wait)
                    continue
                else:
                    raise LLMClientError(f"Gemini request error after {self.max_retries} attempts: {e}") from e
        
        raise LLMClientError(f"Gemini max retries exceeded") from last_exception


class DeepSeekClient(BaseLLMClient):
    """Client for DeepSeek API."""

    def __init__(self):
        super().__init__(
            api_key=settings.deepseek_api_key,
            base_url="https://api.deepseek.com",
            model_id=settings.weak_model_id,
            price_per_token=DEEPSEEK_PRICE_PER_TOKEN,
        )

    async def chat_completion(self, messages: list, **kwargs) -> LLMResponse:
        """
        Get a chat completion from DeepSeek.
        """
        payload = {
            "model": self.model_id,
            "messages": messages,
            "stream": False,
        }
        payload.update(kwargs)

        data = await self._request_with_retry("/chat/completions", payload)

        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage")
        # Calculate cost based on token usage and price per token
        total_tokens = usage.get("total_tokens", 0) if usage else 0
        cost = total_tokens * self.price_per_token

        return LLMResponse(
            content=content,
            model=self.model_id,
            usage=usage,
            cost=cost,
        )


class AnthropicClient(BaseLLMClient):
    """Client for Anthropic Claude API (Claude Opus 4.5)."""

    def __init__(self):
        super().__init__(
            api_key=settings.anthropic_api_key,
            base_url="https://api.anthropic.com",
            model_id=settings.strong_model_id,
            price_per_token=CLAUDE_OPUS_PRICE_PER_TOKEN,
            auth_header_type="x-api-key",  # Anthropic uses x-api-key header
        )

    async def chat_completion(self, messages: list, **kwargs) -> LLMResponse:
        """
        Get a chat completion from Anthropic Claude.
        Note: Anthropic's API uses a different message format (system, user, assistant).
        We'll adapt the OpenAI‑style messages to Anthropic's format.
        """
        # Convert messages to Anthropic format
        system_prompt = None
        system_messages = []
        conversation = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                system_messages.append(content)
            elif role == "user":
                conversation.append({"role": "user", "content": content})
            elif role == "assistant":
                conversation.append({"role": "assistant", "content": content})

        # Anthropic API only allows one system message, so concatenate if multiple
        final_system_prompt = "\n\n".join(system_messages) if system_messages else None

        payload = {
            "model": self.model_id,
            "messages": conversation,
            "max_tokens": 4096,
            "stream": False,
        }
        
        # Only add system if it's not None
        if final_system_prompt:
            payload["system"] = final_system_prompt
        
        payload.update(kwargs)

        data = await self._request_with_retry("/v1/messages", payload)

        content = data["content"][0]["text"]
        usage = data.get("usage")
        # Calculate cost: input + output tokens
        input_tokens = usage.get("input_tokens", 0) if usage else 0
        output_tokens = usage.get("output_tokens", 0) if usage else 0
        total_tokens = input_tokens + output_tokens
        cost = total_tokens * self.price_per_token

        return LLMResponse(
            content=content,
            model=self.model_id,
            usage=usage,
            cost=cost,
        )


# Global client instances (singleton pattern)
_deepseek_client: Optional[DeepSeekClient] = None
_anthropic_client: Optional[AnthropicClient] = None
_gemini_backup1_client: Optional['GeminiClient'] = None
_gemini_backup2_client: Optional['GeminiClient'] = None
_gemini_flash_latest_client: Optional['GeminiClient'] = None


async def get_deepseek_client() -> DeepSeekClient:
    """Get or create the DeepSeek client instance."""
    global _deepseek_client
    if _deepseek_client is None:
        _deepseek_client = DeepSeekClient()
    return _deepseek_client


async def get_anthropic_client() -> AnthropicClient:
    """Get or create the Anthropic client instance."""
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = AnthropicClient()
    return _anthropic_client


async def get_gemini_backup1_client() -> 'GeminiClient':
    """Get or create the Gemini Backup 1 client instance (gemini-2.5-flash)."""
    global _gemini_backup1_client
    if _gemini_backup1_client is None:
        _gemini_backup1_client = GeminiClient(
            api_key=settings.gemini_backup1_api_key,
            model_id="gemini-2.5-flash"
        )
    return _gemini_backup1_client


async def get_gemini_backup2_client() -> 'GeminiClient':
    """Get or create the Gemini Backup 2 client instance (gemini-2.5-flash-lite)."""
    global _gemini_backup2_client
    if _gemini_backup2_client is None:
        _gemini_backup2_client = GeminiClient(
            api_key=settings.gemini_backup2_api_key,
            model_id="gemini-2.5-flash-lite"
        )
    return _gemini_backup2_client


async def get_gemini_flash_latest_client() -> 'GeminiClient':
    """Get or create the Gemini Flash Latest client instance."""
    global _gemini_flash_latest_client
    if _gemini_flash_latest_client is None:
        _gemini_flash_latest_client = GeminiClient(
            api_key=settings.gemini_backup1_api_key,  # Reuse key 1
            model_id="gemini-flash-latest"
        )
    return _gemini_flash_latest_client


async def close_clients():
    """Close all client connections."""
    global _deepseek_client, _anthropic_client, _gemini_backup1_client, _gemini_backup2_client, _gemini_flash_latest_client
    if _deepseek_client:
        await _deepseek_client.close()
        _deepseek_client = None
    if _anthropic_client:
        await _anthropic_client.close()
        _anthropic_client = None
    if _gemini_backup1_client:
        await _gemini_backup1_client.close()
        _gemini_backup1_client = None
    if _gemini_backup2_client:
        await _gemini_backup2_client.close()
        _gemini_backup2_client = None
    if _gemini_flash_latest_client:
        await _gemini_flash_latest_client.close()
        _gemini_flash_latest_client = None