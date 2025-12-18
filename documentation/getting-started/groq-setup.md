# Groq Provider Setup

## Overview

Groq is a quota-based free tier LLM provider optimized for **local/personal usage**. It offers extremely fast inference with OpenAI-compatible API endpoints.

## Key Characteristics

### **NOT Free Models**
- Groq does NOT have "free models"
- Groq offers a **FREE USAGE TIER** (quota-based)
- The SAME models are used for free and paid accounts
- Free users are **rate-limited** (HTTP 429), **not billed**
- When quota is exhausted, requests return 429 and gracefully fall back to the next model

### Performance
- Ultra-fast inference (~500-1000 tokens/second)
- Low latency ideal for interactive applications
- Rate-limited at ~30 RPM for free tier

## Supported Models

### Production Models (Groq Free Tier)

1. **llama-3.1-8b-instant** (Primary)
   - Meta Llama 3.1 8B
   - Fastest model (~560 tps)
   - Best for quick responses and coding
   - 131K context window

2. **llama-3.3-70b-versatile** (Better Reasoning)
   - Meta Llama 3.3 70B
   - Stronger reasoning capabilities
   - Good for complex queries
   - 32K context window

3. **qwen/qwen3-32b** (Fallback)
   - Alibaba Qwen 3 32B
   - Alternative reasoning model
   - Large 131K context window

## Configuration

### 1. Get Groq API Key

Sign up at [https://console.groq.com](https://console.groq.com) and create an API key.

### 2. Add to `.env`

```bash
GROQ_API_KEY=gsk_your_groq_api_key_here
```

### 3. Model Configuration

Groq models are pre-configured in `config/models_config.json` with:
- `provider: "groq"`
- `order: 2` (priority tier for weak models)
- Zero cost (quota-based, not billed)

### 4. Routing Behavior

**Weak Model Order:**
```
1. deepseek-chat (order 1, fastest paid)
2. groq-llama-3.1-8b-instant (order 2, quota-based)
3. groq-llama-3.3-70b-versatile (order 2, quota-based)
4. gemini-2.5-flash-lite-primary (order 3, free tier)
5. openrouter models (order 3, free tier)
6. groq-qwen-3-32b (order 3, fallback)
```

**Judge Model Order:**
```
1. gemini-2.5-flash-lite-primary
2. groq-llama-3.3-70b-versatile
3. groq-llama-3.1-8b-instant
4. openrouter models
5. groq-qwen-3-32b
6. deepseek-judge-backup1
```

## Rate Limiting

### Free Tier Limits
- **RPM**: ~30 requests/minute
- **TPM**: ~30,000 tokens/minute
- **RPD**: ~14,400 requests/day (estimated)

### Failure Handling
- If `GROQ_API_KEY` is missing → Groq models skipped
- If Groq returns 429 → immediately fall back to next model
- **No aggressive retries** (quota-based service)

## Testing

Run the Groq integration test:

```bash
python3 scripts/test_groq_models.py
```

Expected output:
```
✅ PASS - Llama 3.1 8B Instant (Primary weak model)
✅ PASS - Llama 3.3 70B Versatile (Better reasoning)
✅ PASS - Qwen 3 32B (Fallback)

🎉 All Groq models working correctly!
```

## Usage Example

### Via REST API

```bash
curl -X POST http://localhost:8000/route \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Write a Python function to calculate factorial",
    "session_id": "test-session",
    "use_judge": false
  }'
```

If DeepSeek fails or is rate-limited, the router will automatically try Groq models next.

### Model-Specific Request

To explicitly use a Groq model:

```bash
curl -X POST http://localhost:8000/route \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Explain async/await in Python",
    "session_id": "test-session",
    "model_id": "groq-llama-3.1-8b-instant"
  }'
```

## Cost Tracking

- All Groq models return `cost: 0.0`
- Usage is tracked in `usage.total_tokens`
- No billing charges (quota-limited instead)

## Monitoring

Check Groq usage via the dashboard:

```bash
curl http://localhost:8000/dashboard/session/YOUR_SESSION_ID
```

Look for:
- `model_history` to see which Groq models were used
- `total_cost` (should remain 0.0 for Groq calls)
- `attempts_made` to track fallback behavior

## Troubleshooting

### Error: "Groq API key not configured"

**Solution**: Add `GROQ_API_KEY` to `.env` file

### Error: HTTP 429 Rate Limit

**Expected Behavior**: Router automatically falls back to next model in order.

**Check**: View logs to confirm fallback:
```bash
tail -f logs/sentinelrouter.log | grep -i groq
```

### Models Not Available

If Groq models are skipped, verify:
1. `GROQ_API_KEY` is set in `.env`
2. API key is valid (test with `scripts/test_groq_models.py`)
3. Check model status in `config/models_config.json`

## Best Practices

1. **Use for Development/Personal Projects**
   - Groq's free tier is ideal for local development
   - Not recommended for high-volume production use

2. **Configure Fallbacks**
   - Always have backup models configured
   - Groq rate limits are strict but predictable

3. **Monitor Usage**
   - Track daily request counts
   - Adjust routing order if hitting limits frequently

4. **Don't Retry Aggressively**
   - The client already has limited retries (max 1)
   - Let the router handle fallback logic

## Architecture Notes

### Client Implementation
- Located in `sentinelrouter/sentinelrouter/clients.py`
- Class: `GroqClient`
- Base URL: `https://api.groq.com/openai/v1`
- OpenAI-compatible request/response format

### Provider Resolution
- Located in `sentinelrouter/sentinelrouter/router_logic.py`
- Checks `provider == "groq"` to route to Groq client
- Dynamically creates client with model key

### No Dependencies Added
- Uses existing `httpx` client
- No new packages required
- Follows existing provider patterns

## Related Documentation

- [Model Configuration](./configuration.md)
- [OpenRouter Setup](./openrouter-setup.md) (similar quota-based provider)
- [Rate Limiting Implementation](../architecture/rate-limiting-implementation.md)
- [Routing Logic](../architecture/routing-logic.md)
