# Roo → SentinelRouter Setup

## Configuration Values

```
Base URL: http://localhost:8000/v1
API Key: (leave empty or use dummy value)
Model: gpt-4
```

## Usage Example

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Session-ID: roo-session" \
  -d '{
    "messages": [{"role": "user", "content": "test"}]
  }'
```

**Note**: Server automatically routes to DeepSeek (cheap) or Anthropic (expensive) based on complexity. The `model` field is ignored.
