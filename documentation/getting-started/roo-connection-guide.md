# Connecting Roo Code to SentinelRouter

## Server Status ✅

Your SentinelRouter server is **running on Docker** at:
- **URL**: `http://localhost:8000`
- **Status**: Healthy ✅
- **API Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## Quick Connection for Roo Code

### 1. **Main Chat Endpoint** (OpenAI Compatible)

**Endpoint**: `POST http://localhost:8000/v1/chat/completions`

**Headers**:
```
Content-Type: application/json
X-Session-ID: your-session-id-here  (optional but recommended)
```

**Request Body**:
```json
{
  "model": "gpt-4",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello, how are you?"}
  ],
  "temperature": 0.7,
  "session_id": "roo-session-123"
}
```

**Response** (OpenAI Compatible):
```json
{
  "id": "chatcmpl-xyz123",
  "object": "chat.completion",
  "created": 1702345678,
  "model": "deepseek-chat",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! I'm doing well, thank you..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 15,
    "completion_tokens": 20,
    "total_tokens": 35
  }
}
```

---

## 2. **Available Endpoints**

### Health Check
```bash
GET http://localhost:8000/health
```
Returns: `{"status": "healthy", "service": "sentinelrouter"}`

### Metrics
```bash
GET http://localhost:8000/metrics
```
Returns overall system metrics (requests, cost, escalation rate)

### Session Details
```bash
GET http://localhost:8000/sessions/{session_id}
```
Returns details for a specific session

### Audit Trail
```bash
GET http://localhost:8000/audit/{session_id}
```
Returns routing decisions for a session

---

## 3. **Configuring Roo to Use SentinelRouter**

### Option A: Direct Configuration (if Roo supports custom OpenAI base URL)

**Base URL**: `http://localhost:8000/v1`

Configure Roo with:
```
OPENAI_API_BASE_URL=http://localhost:8000/v1
OPENAI_API_KEY=dummy-key-not-used
```

The API key is not validated by SentinelRouter (it uses its own configured keys).

### Option B: Custom HTTP Client

Create a wrapper that sends requests to:
```
http://localhost:8000/v1/chat/completions
```

---

## 4. **Testing the Connection**

### Using curl:
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Session-ID: roo-test-session" \
  -d '{
    "model": "gpt-4",
    "messages": [
      {"role": "user", "content": "Say hello"}
    ]
  }'
```

### Using Python:
```python
import requests

response = requests.post(
    "http://localhost:8000/v1/chat/completions",
    headers={
        "Content-Type": "application/json",
        "X-Session-ID": "roo-session-123"
    },
    json={
        "model": "gpt-4",
        "messages": [
            {"role": "user", "content": "Hello!"}
        ]
    }
)

print(response.json())
```

### Using httpx (async):
```python
import httpx
import asyncio

async def test_sentinelrouter():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/v1/chat/completions",
            headers={"X-Session-ID": "roo-session"},
            json={
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "Hello"}]
            }
        )
        print(response.json())

asyncio.run(test_sentinelrouter())
```

---

## 5. **How SentinelRouter Works**

When Roo sends a request:

1. **Judge evaluates** the prompt complexity (using DeepSeek → Anthropic → Gemini backups)
2. **Router decides** which model to use:
   - **Weak model** (DeepSeek) for simple requests (cheap, fast)
   - **Strong model** (Claude Opus) for complex requests (expensive, powerful)
3. **Budget tracking** prevents overspending per session
4. **Circuit breaker** protects against failing providers
5. **Automatic failover** to backup models if primary fails

---

## 6. **Session Management**

### Create a persistent session:
Include the same `session_id` in the header or request body:
```
X-Session-ID: roo-persistent-session
```

**Benefits**:
- Tracks total cost per session
- Enforces budget limits (`MAX_COST_PER_SESSION`)
- Maintains escalation rate history
- Enables audit trail

### Without session ID:
If you don't provide a session ID, one will be auto-generated per request.

---

## 7. **Monitoring Your Usage**

### Check session metrics:
```bash
curl http://localhost:8000/sessions/roo-session-123
```

Returns:
```json
{
  "session_id": "roo-session-123",
  "current_cost": 0.05,
  "max_cost_per_session": 10.0,
  "total_requests": 15,
  "strong_requests": 2,
  "weak_requests": 13,
  "escalation_rate": 0.133
}
```

### Check overall metrics:
```bash
curl http://localhost:8000/metrics
```

Returns:
```json
{
  "requests_total": 150,
  "sessions_total": 10,
  "cost_total": 2.35,
  "escalation_rate": 0.12,
  "strong_requests": 18,
  "weak_requests": 132
}
```

---

## 8. **API Documentation**

**Interactive API docs** are available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

Open these in your browser to explore all endpoints interactively.

---

## 9. **Important Notes**

### OpenAI Compatibility
SentinelRouter implements the OpenAI chat completions API format, so:
- ✅ Works with OpenAI SDKs (just change base URL)
- ✅ Compatible with tools expecting OpenAI format
- ✅ Roo can treat it like OpenAI API

### Model Selection
The `model` field in your request is **ignored**. SentinelRouter:
- Uses its **judge system** to evaluate complexity
- **Automatically routes** to appropriate model (weak or strong)
- Returns the actual model used in the response

### Budget Protection
- Default limit: **$10 per session**
- Configurable via `MAX_COST_PER_SESSION` env var
- Returns **402 Budget Exceeded** when limit reached

---

## 10. **Stopping/Starting the Server**

### Check status:
```bash
docker ps --filter "name=sentinelrouter"
```

### Stop server:
```bash
docker compose down
```

### Start server:
```bash
docker compose up -d
```

### View logs:
```bash
docker compose logs -f sentinelrouter
```

### Restart server:
```bash
docker compose restart sentinelrouter
```

---

## Quick Start Checklist

- [x] Server is running on Docker ✅
- [ ] Test connection: `curl http://localhost:8000/health`
- [ ] Send test request: `curl -X POST http://localhost:8000/v1/chat/completions ...`
- [ ] Configure Roo to use `http://localhost:8000/v1` as base URL
- [ ] Include `X-Session-ID` header for session tracking
- [ ] Monitor usage via `/sessions/{id}` and `/metrics` endpoints

---

## Support

- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health
- **Metrics**: http://localhost:8000/metrics

Your SentinelRouter is ready to receive requests from Roo! 🚀
