# Judge Mode Optimization - Feature Documentation

## Overview

The Judge Mode Optimization feature provides three modes for controlling when the judge is called, allowing you to optimize for latency, cost, or safety based on your needs.

## Motivation

Previously, the judge was called for **every request**, which:
- Added 200-500ms latency per request
- Increased API costs (external judge model calls)
- Was unnecessary for simple queries that weak models handle well

With Judge Mode Optimization, you can:
- **Skip judge calls** for known-simple queries → Save latency & cost
- **Defer judge calls** until needed → Best balance of speed and safety
- **Force judge calls** when you need strong guarantees → Maximum safety

## Three Judge Modes

### Mode 1: `use_judge=true` - Always Call Judge (Legacy Mode)

**When to use:**
- Maximum safety required
- All requests need complexity evaluation
- Cost/latency not a concern

**Behavior:**
```
Request → Judge → Routing Decision → Model Call → Response
  ~500ms   ~200ms     instant         ~2-10s      instant
```

**API Example:**
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Explain quantum computing"}],
    "use_judge": true
  }'
```

### Mode 2: `use_judge=false` - Skip Judge (Fast Mode)

**When to use:**
- Known-simple queries (FAQ, basic lookups)
- Latency-critical applications
- Cost optimization for high-volume traffic

**Behavior:**
```
Request → Weak Model → Response
  ~500ms    ~2-5s      instant
```

Judge is skipped entirely, weak model is used automatically.

**API Example:**
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "What is 2+2?"}],
    "use_judge": false
  }'
```

### Mode 3: `use_judge=null` - Conditional Mode (Default, Recommended)

**When to use:**
- General-purpose routing (recommended default)
- Balance of speed and safety
- Unknown query complexity

**Behavior:**
```
Request → Weak Model (with 15s timeout)
  ~500ms    ├─ Completes in <15s → Response (no judge call)
            └─ Takes >15s → Call Judge
                             ├─ Judge says "weak OK" → Wait for weak model
                             └─ Judge says "strong" → Escalate to strong model
```

**API Example:**
```bash
# Omit use_judge field (defaults to null/conditional mode)
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Help me debug this code..."}]
  }'
```

## Timeout-Based Escalation (Conditional Mode)

When `use_judge=null` (conditional mode):

1. **Fast Request Flow (Most Common):**
   ```
   Request → Weak Model completes in 5s → Response
   Judge: NOT CALLED ✓ (saved ~200ms + API cost)
   ```

2. **Slow Request Flow (Complex Query):**
   ```
   Request → Weak Model running... 
          → 15s timeout!
          → Call Judge
          → Judge returns: complexity=0.9, impact=HIGH
          → Cancel weak model
          → Escalate to strong model
          → Strong model completes → Response
   Judge: CALLED (necessary for complex query)
   ```

3. **Slow But Simple Flow (Rare):**
   ```
   Request → Weak Model running...
          → 15s timeout!
          → Call Judge
          → Judge returns: complexity=0.2, impact=LOW
          → Wait for weak model to complete
          → Weak model finishes → Response
   Judge: CALLED (but stayed with weak model)
   ```

## Performance Impact

### Latency Comparison

| Mode | Simple Query | Complex Query |
|------|--------------|---------------|
| `use_judge=true` (legacy) | ~2.7s (judge + weak) | ~8.2s (judge + strong) |
| `use_judge=false` | ~2.5s (weak only) | ~2.5s (weak, might fail) |
| `use_judge=null` (conditional) | **~2.5s** (weak only) | ~8.2s (judge + strong) |

**Savings:** Conditional mode saves ~200ms on simple queries (50-80% of traffic).

### Cost Comparison

Assuming:
- 1000 requests/day
- 70% simple queries, 30% complex queries

| Mode | Judge Calls/Day | Cost Impact |
|------|-----------------|-------------|
| `use_judge=true` | 1000 | 100% baseline |
| `use_judge=false` | 0 | 0% (but risks using wrong model) |
| `use_judge=null` | ~300 | **30%** (only complex queries) |

**Savings:** Conditional mode reduces judge costs by ~70%.

## Metrics & Monitoring

### New Metrics Added

1. **`judge_skip`** - Tracks when judge is skipped
   ```json
   {
     "type": "judge_skip",
     "session_id": "session_123",
     "reason": "explicit_skip_use_judge_false" | "conditional_mode_deferred"
   }
   ```

2. **`judge_timeout_escalation`** - Tracks timeout-based escalations
   ```json
   {
     "type": "judge_timeout_escalation",
     "session_id": "session_123",
     "model_id": "deepseek-chat",
     "timeout_ms": 15000
   }
   ```

### Monitoring Recommendations

**Key Metrics to Watch:**
- `judge_skip` count → Should be ~70% in conditional mode
- `judge_timeout_escalation` count → Should be ~5-10% in conditional mode
- Average latency by mode → Track improvements

**Dashboard Queries:**
```sql
-- Judge skip rate (should be high in conditional mode)
SELECT 
  COUNT(CASE WHEN type='judge_skip' THEN 1 END) * 100.0 / COUNT(*) as skip_rate
FROM metrics
WHERE type IN ('judge_skip', 'judge_latency')

-- Timeout escalation rate (should be low ~5-10%)
SELECT 
  COUNT(*) as escalations,
  AVG(timeout_ms) as avg_timeout
FROM metrics
WHERE type = 'judge_timeout_escalation'
```

## Best Practices

### When to Use Each Mode

| Use Case | Recommended Mode | Why |
|----------|------------------|-----|
| FAQ/Help system | `use_judge=false` | Known-simple queries |
| Code generation | `use_judge=true` | Need strong model guarantees |
| General chatbot | `use_judge=null` | Balanced approach |
| Streaming responses | `use_judge=false` or `true` | Conditional mode incompatible with streaming |
| Rate-limited APIs | `use_judge=false` | Reduce external calls |
| SLA-critical | `use_judge=null` | Best latency without sacrificing quality |

### Migration Guide

**Existing applications (using legacy always-call-judge):**

1. **No changes required** - Default behavior is now conditional mode
2. **To keep legacy behavior:** Set `use_judge=true` on all requests
3. **To optimize:** Leave `use_judge` unset (conditional mode)

**Example Migration:**
```python
# Before (implicit)
response = client.chat_completions(messages=[...])

# After - Option 1: No change (gets conditional mode - recommended)
response = client.chat_completions(messages=[...])

# After - Option 2: Explicit legacy mode
response = client.chat_completions(
    messages=[...],
    use_judge=True  # Force legacy behavior
)

# After - Option 3: Aggressive optimization
response = client.chat_completions(
    messages=[...],
    use_judge=False  # Skip judge for known-simple queries
)
```

## Configuration

### Request-Level Control

Set `use_judge` field in chat completion request:

```python
# Python SDK example
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1")

# Conditional mode (default)
response = client.chat.completions.create(
    model="gpt-4",  # Ignored - router decides
    messages=[{"role": "user", "content": "Hello"}],
    extra_body={"use_judge": None}  # or omit field
)

# Skip judge
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}],
    extra_body={"use_judge": False}
)

# Always use judge
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}],
    extra_body={"use_judge": True}
)
```

### Global Configuration

To disable judge globally (equivalent to `use_judge=false` for all requests):

```json
// config/models_config.json
{
  "judge_config": {
    "is_judge_required": false,
    "model_order": ["gemini-2.5-flash-lite-primary", "deepseek-judge-backup1"]
  }
}
```

**Note:** Request-level `use_judge` overrides global `is_judge_required`.

## Testing

### Unit Tests

Run judge mode optimization tests:
```bash
pytest tests/test_judge_mode_optimization.py -v
```

### Integration Testing

```python
import asyncio
from sentinelrouter.sentinelrouter.router_logic import route_request

async def test_modes():
    # Test use_judge=false
    result = await route_request(
        session_id="test",
        prompt="Simple query",
        messages=[{"role": "user", "content": "What is 2+2?"}],
        use_judge=False
    )
    assert "Judge skipped" in result["reasoning"]
    
    # Test use_judge=true
    result = await route_request(
        session_id="test",
        prompt="Complex query",
        messages=[{"role": "user", "content": "Explain quantum mechanics"}],
        use_judge=True
    )
    assert result["complexity_score"] > 0
    
    # Test use_judge=None (conditional)
    result = await route_request(
        session_id="test",
        prompt="Unknown complexity",
        messages=[{"role": "user", "content": "Help me debug..."}],
        use_judge=None
    )
    # Judge may or may not be called depending on weak model latency

asyncio.run(test_modes())
```

## Troubleshooting

### Issue: Weak model timing out frequently

**Symptom:** High `judge_timeout_escalation` rate (>20%)

**Causes:**
- Weak model too slow for your workload
- 15s timeout too aggressive
- Network latency issues

**Solutions:**
1. Switch to `use_judge=true` for complex queries
2. Adjust timeout (requires code change - see `router_logic.py:260`)
3. Use faster weak model

### Issue: Quality degradation

**Symptom:** Users report poor responses after enabling conditional mode

**Causes:**
- Too many requests using `use_judge=false`
- Weak model not suitable for your use case

**Solutions:**
1. Switch to `use_judge=null` (conditional mode) instead of `false`
2. Review query patterns - use `use_judge=true` for complex domains
3. Monitor strong model usage rate - should be ~20-30%

### Issue: No latency improvement

**Symptom:** Latency same before/after enabling optimization

**Causes:**
- Most queries are complex (timeout → judge called anyway)
- Not actually using conditional/skip mode

**Solutions:**
1. Check metrics: `judge_skip` count should be high
2. Verify `use_judge` field is set correctly
3. Consider if your workload benefits from optimization

## Related Features

- **Semantic Cache**: Caches judge results per prompt hash
- **Budget Killswitch**: Honors budget limits before calling judge
- **Cycle Detection**: Overrides judge decision if cycle detected

## Future Enhancements

Potential future improvements:
- Configurable timeout threshold (currently hardcoded at 15s)
- Per-model timeout configuration
- ML-based timeout prediction
- Cache judge results by prompt similarity

## See Also

- [ISSUE_Judge_Mode_Optimization.md](./.github/ISSUE_Judge_Mode_Optimization.md)
- [Router Architecture](./sentinelrouter_design.md)
- [Metrics Documentation](./METRICS_IMPLEMENTATION.md)
