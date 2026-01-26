"""
Real integration tests that make actual API calls.

These tests verify the system works with real providers.
They are conservative with token usage - single simple queries only.
"""

import pytest
import os
from sentinelrouter.sentinelrouter.clients import (
    get_deepseek_client,
    get_anthropic_client,
)


@pytest.mark.asyncio
async def test_deepseek_api_connection():
    """
    Minimal integration test: Verify DeepSeek API connection works.
    
    Token usage: ~20 tokens (minimal cost: ~$0.00003)
    """
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        pytest.skip("DEEPSEEK_API_KEY not configured")

    # Get DeepSeek client
    client = await get_deepseek_client()

    # Make minimal API call
    messages = [{"role": "user", "content": "Say 'OK'"}]
    response = await client.chat_completion(messages)

    # Verify response
    assert response is not None
    assert response.content is not None
    assert len(response.content) > 0
    assert response.model is not None
    assert response.usage["total_tokens"] > 0

    print(
        f"✅ DeepSeek API test passed - Used {response.usage['total_tokens']} tokens, Cost: ${response.cost:.6f}"
    )


@pytest.mark.asyncio
async def test_anthropic_api_connection():
    """
    Minimal integration test: Verify Anthropic API connection works.
    
    Token usage: ~20 tokens (minimal cost: ~$0.00006)
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not configured")

    # Get Anthropic client
    client = await get_anthropic_client()

    # Make minimal API call
    messages = [{"role": "user", "content": "Say 'OK'"}]
    response = await client.chat_completion(messages)

    # Verify response
    assert response is not None
    assert response.content is not None
    assert len(response.content) > 0
    assert response.model is not None
    assert response.usage["total_tokens"] > 0

    print(
        f"✅ Anthropic API test passed - Used {response.usage['total_tokens']} tokens, Cost: ${response.cost:.6f}"
    )

