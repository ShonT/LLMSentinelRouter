# Adding New Models

This guide explains how to add new LLM models to the SentinelRouter system, covering configuration, provider integration, and testing.

## Overview

SentinelRouter supports multiple LLM providers through a unified configuration system. Adding a new model involves:

1. **Configuration** - Adding model details to `config/models_config.json`
2. **Provider Client** - Implementing or using an existing client in `sentinelrouter/clients.py`
3. **Model Registration** - The system automatically registers models from config
4. **Testing** - Verifying the model works in routing and failure scenarios

## Prerequisites

- Understanding of the [configuration schema](../getting-started/configuration.md)
- Access to the model's API key and endpoint
- Basic knowledge of the provider's API (OpenAI-compatible, Anthropic, Gemini, etc.)

## Step 1: Add Model to Configuration

Edit `config/models_config.json` and add a new entry to the `models` object.

### Configuration Structure

Each model must follow the `ModelConfig` schema defined in `sentinelrouter/schemas/config_models.py`:

```json
"your-model-key": {
  "display_name": "Human Readable Name",
  "provider": "provider_id",
  "model_definition": "Description of model capabilities",
  "model_key": "actual-model-id-for-api",
  "status": "ACTIVE",
  "capabilities": {
    "modality": ["text"],
    "context_window": 128000
  },
  "routing": {
    "priority_group": "fast_tier" | "strong_tier",
    "order": 1
  },
  "limits": {
    "requests_per_minute": 60,
    "requests_per_day": 10000,
    "tokens_per_minute": 500000
  },
  "free_tier_limits": { ... },
  "paid_tier_limits": { ... },
  "pricing": {
    "currency": "USD",
    "input_cost_per_m": 0.14,
    "output_cost_per_m": 0.28
  },
  "cost": {
    "per_call": 0.001,
    "per_token_input": 1.4e-07,
    "per_token_output": 2.8e-07
  },
  "state": {
    "current_rpm": 0.0,
    "requests_today": 0,
    "tokens_today": 0,
    "total_cost_session": 0.0
  }
}
```

### Example: Adding OpenAI GPT-4

```json
"gpt-4-turbo": {
  "display_name": "GPT-4 Turbo",
  "provider": "openai",
  "model_definition": "OpenAI GPT-4 Turbo with 128k context",
  "model_key": "gpt-4-turbo",
  "status": "ACTIVE",
  "capabilities": {
    "modality": ["text"],
    "context_window": 128000
  },
  "routing": {
    "priority_group": "strong_tier",
    "order": 2
  },
  "limits": {
    "requests_per_minute": 40,
    "requests_per_day": 5000,
    "tokens_per_minute": 300000
  },
  "free_tier_limits": {
    "requests_per_day": 100,
    "requests_per_minute": 5,
    "tokens_per_minute": 40000,
    "tokens_per_day": 200000
  },
  "paid_tier_limits": {
    "requests_per_day": 5000,
    "requests_per_minute": 40,
    "tokens_per_minute": 300000,
    "tokens_per_day": 2000000
  },
  "pricing": {
    "currency": "USD",
    "input_cost_per_m": 10.0,
    "output_cost_per_m": 30.0
  },
  "cost": {
    "per_call": 0.03,
    "per_token_input": 1.0e-05,
    "per_token_output": 3.0e-05
  },
  "state": {
    "current_rpm": 0.0,
    "requests_today": 0,
    "tokens_today": 0,
    "total_cost_session": 0.0
  }
}
```

## Step 2: Ensure Provider Client Exists

Check if the provider already has a client implementation in `sentinelrouter/clients.py`.

### Supported Providers

- `openai` - Uses `OpenAIClient`
- `anthropic` - Uses `AnthropicClient`
- `deepseek` - Uses `DeepSeekClient`
- `gemini` - Uses `GeminiClient`

### Adding a New Provider

If you need to add a new provider, create a new class extending `BaseLLMClient`:

```python
from .clients import BaseLLMClient, LLMResponse

class NewProviderClient(BaseLLMClient):
    def __init__(self, api_key: str, base_url: str = None):
        super().__init__(api_key, base_url)
        # Initialize SDK
    
    async def chat_completion(self, messages: List[Dict]) -> LLMResponse:
        # Implement API call
        # Return LLMResponse with content, tokens, cost
```

Then update the `create_client` factory function in `sentinelrouter/clients.py` to handle your provider.

## Step 3: Update Model Registry (Optional)

The `ModelRegistry` automatically loads models from configuration. However, you may need to update:

1. **Judge Configuration** - If this model should be used as a judge, add its key to `judge_config.model_order` in `config/models_config.json`
2. **Routing Order** - Add to `routing_order_config.strong_models` or `weak_models` as appropriate

Example judge configuration update:
```json
"judge_config": {
  "model_order": [
    "gemini-2.5-flash-lite-primary",
    "deepseek-judge-backup1",
    "your-new-judge-model"
  ]
}
```

## Step 4: Test the Model

### Manual Testing

1. **Start the server**:
   ```bash
   python -m sentinelrouter.sentinelrouter.server
   ```

2. **Send a test request**:
   ```bash
   curl -X POST http://localhost:8000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer test" \
     -d '{
       "model": "your-model-key",
       "messages": [{"role": "user", "content": "Hello"}]
     }'
   ```

3. **Check dashboard**: Visit `http://localhost:8001` to see if the model appears in the Live Traffic tab.

### Automated Testing

Create a unit test in `tests/unit/test_clients.py`:

```python
async def test_new_model_client():
    """Test that the new model client works correctly."""
    client = create_client(
        provider="new_provider",
        api_key="test_key",
        base_url="http://test.endpoint"
    )
    # Mock the API call and verify response handling
```

Run the test:
```bash
pytest tests/unit/test_clients.py -xvs
```

## Step 5: Update Rate Limits and Budget

### Rate Limiting

The model's rate limits are enforced by `ThrottleManager`. Verify that the limits in configuration match the provider's actual API limits.

### Budget Considerations

Update the `cost` fields accurately to ensure proper budget tracking:

- `per_call`: Fixed cost per API call (if any)
- `per_token_input`: Cost per input token
- `per_token_output`: Cost per output token

These values are used by the `Budget` module to track spending and enforce kill-switches.

## Common Issues and Solutions

### 1. Model Not Appearing in Available Models
- **Cause**: Missing or incorrect `provider` field
- **Fix**: Ensure the provider matches a supported client type

### 2. 401 Unauthorized Errors
- **Cause**: Invalid API key or base URL
- **Fix**: Check environment variables and client initialization

### 3. Model Always Exhausted
- **Cause**: Rate limits set too low
- **Fix**: Adjust `requests_per_minute` and `tokens_per_minute` in configuration

### 4. Incorrect Cost Calculation
- **Cause**: Wrong `cost` or `pricing` values
- **Fix**: Verify against provider's pricing page and update configuration

## Best Practices

1. **Start with Test Configuration**: Add new models with conservative limits initially
2. **Use Environment Variables**: Store API keys in `.env` file, not in configuration
3. **Monitor Closely**: Watch dashboard metrics for the first 24 hours
4. **Implement Circuit Breaker**: The system automatically fails over, but verify backup models work
5. **Update Documentation**: Keep this guide and configuration comments up to date

## Example: Complete Workflow for Adding Claude 3.5 Sonnet

1. **Add to `config/models_config.json`**:
   ```json
   "claude-3-5-sonnet": {
     "display_name": "Claude 3.5 Sonnet",
     "provider": "anthropic",
     "model_key": "claude-3-5-sonnet-20241022",
     ...
   }
   ```

2. **Ensure `ANTHROPIC_API_KEY` is set in environment**

3. **Test with curl**:
   ```bash
   curl -X POST http://localhost:8000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "claude-3-5-sonnet",
       "messages": [{"role": "user", "content": "Hello, Claude!"}]
     }'
   ```

4. **Verify in dashboard** at `http://localhost:8001`

5. **Run integration tests**:
   ```bash
   pytest tests/integ/test_backup_weak_models_demo.py -k "claude"
   ```

## Next Steps

- Review [Configuration Guide](../getting-started/configuration.md) for advanced settings
- Learn about [Routing Logic](../architecture/routing-logic.md) to understand how your model will be used
- Set up [Monitoring](../operations/monitoring.md) for the new model

---

**Need Help?**  
- Check existing provider implementations in `sentinelrouter/clients.py`
- Review test files for examples
- Open an issue in the repository for support