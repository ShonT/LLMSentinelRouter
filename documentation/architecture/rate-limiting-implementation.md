# Rate Limiting Implementation Summary

## Overview

Implemented comprehensive sliding window rate limiting to prevent excessive API throttling (429 errors) by proactively checking and enforcing rate limits **before** making API calls.

## Changes Made

### 1. **New Module: `rate_limiter.py`**

**Location**: `sentinelrouter/sentinelrouter/rate_limiter.py`

**Features**:
- **Sliding window tracking** using `collections.deque` for efficient time-windowed request/token counting
- **Per-model tracking** with independent windows for each LLM model
- **Multiple limit types**:
  - Requests per minute (RPM)
  - Tokens per minute (TPM)
  - Requests per day (RPD)
  - Tokens per day (TPD)
- **Safety margin** (default 95%) to prevent edge cases where concurrent requests push over limit
- **Automatic daily reset** at midnight UTC via background task
- **Thread-safe** with asyncio locks for concurrent access
- **Projected token checking** - estimates if upcoming request would exceed TPM

**Key Classes**:
- `RateLimitWindow`: Per-model sliding window tracker
- `RateLimiter`: Global rate limiter managing all models
- `get_rate_limiter()`: Singleton accessor

**Configuration**:
```python
rate_limiter = get_rate_limiter(safety_margin=0.95)  # Use 95% of limits
```

### 2. **Router Logic Integration**

**File**: `sentinelrouter/sentinelrouter/router_logic.py`

**Changes**:

#### Import and Initialization (Line ~35):
```python
from .rate_limiter import get_rate_limiter
rate_limiter = get_rate_limiter(safety_margin=0.95)
```

#### Preemptive Rate Limit Checking (Lines ~304-350):
**Replaced** old placeholder RPM check (`current_rpm=1` comment) with:

```python
# Estimate tokens for this request
estimated_tokens = len(prompt.split()) * 2  # ~2 tokens per word

# Check rate limits using sliding window rate limiter
allowed, limit_reason, usage_stats = await rate_limiter.check_rate_limits(
    model_id=model_id,
    rpm_limit=active_limits.requests_per_minute,
    tpm_limit=active_limits.tokens_per_minute,
    rpd_limit=active_limits.requests_per_day,
    tpd_limit=getattr(active_limits, 'tokens_per_day', None),
    estimated_tokens=estimated_tokens
)

if not allowed:
    logger.warning(f"Model {model_id} rate limit check failed: {limit_reason} | Usage: ...")
    metrics.record_event("rate_limit_preemptive_skip", {...})
    continue  # Skip to next model
```

**Benefits**:
- Skips models **before** API call if limits would be exceeded
- Logs detailed usage statistics for debugging
- Records metrics for dashboard visibility

#### Request Recording After API Call (Lines ~438-452):
**Added** accurate token tracking:

```python
# Update rate limiter with actual tokens used
await rate_limiter.record_request(model_id, total_tokens)
```

**Replaced** hardcoded `current_rpm=1` with actual rate limiter tracking.

#### Enhanced 429 Error Logging (Lines ~520-550):
**Added** detailed rate limit type detection and usage logging:

```python
# Determine rate limit type from error message
limit_type = "unknown"
if any(kw in error_msg for kw in ['token', 'tpm', 'tokens per minute']):
    limit_type = "tokens_per_minute"
elif any(kw in error_msg for kw in ['request', 'rpm', 'requests per minute']):
    limit_type = "requests_per_minute"
elif any(kw in error_msg for kw in ['daily', 'quota', 'day']):
    limit_type = "daily_quota"

# Get current usage for context
usage_stats = await rate_limiter.get_usage_stats(model_id)

logger.error(
    f"Model {model_id} hit rate limit (429): {limit_type} | "
    f"Current usage: RPM={usage_stats['requests_last_minute']}, TPM=... "
)

metrics.record_event("rate_limit_429_error", {...})
```

### 3. **Server Lifecycle Management**

**File**: `sentinelrouter/sentinelrouter/server.py`

**Changes** (Lines ~136-160):

#### Startup Event:
```python
@app.on_event("startup")
async def startup_event():
    init_db()
    
    # Start rate limiter daily reset task
    from .rate_limiter import get_rate_limiter
    rate_limiter = get_rate_limiter()
    rate_limiter.start()
    logger.info("Rate limiter started.")
```

#### Shutdown Event:
```python
@app.on_event("shutdown")
async def shutdown_event():
    from .rate_limiter import get_rate_limiter
    
    # Stop rate limiter
    rate_limiter = get_rate_limiter()
    await rate_limiter.stop()
    
    await close_clients()
```

### 4. **Metrics Enhancements**

**File**: `sentinelrouter/sentinelrouter/metrics.py`

**New Methods** (Lines ~260-300):

```python
def record_event(self, event_type: str, data: Dict[str, Any]):
    """Generic event recording for arbitrary metrics."""
    
def record_rate_limit_preemptive_skip(
    self, model_id, tier, limit_type, current_usage, limit_values
):
    """Record when model skipped due to preemptive rate limit check."""
    
def record_rate_limit_429_error(
    self, model_id, limit_type, error_message, current_usage
):
    """Record when model returns 429 rate limit error."""
```

**Dashboard Visibility**:
- `rate_limit_preemptive_skip`: Models skipped before API call
- `rate_limit_429_error`: Actual 429 errors received (should decrease)
- Detailed usage statistics in event data

### 5. **Comprehensive Unit Tests**

**File**: `tests/test_rate_limiter.py`

**Test Coverage**:
- ✅ Adding requests to windows
- ✅ Automatic cleanup of expired entries
- ✅ RPM limit enforcement
- ✅ TPM limit enforcement
- ✅ RPD limit enforcement
- ✅ Daily counter reset mechanism
- ✅ Multiple model tracking
- ✅ Estimated token projection
- ✅ Safety margin behavior
- ✅ Concurrent access thread-safety

**Results**: 13/13 tests passing

## How It Works

### Flow Diagram

```
1. Request arrives
   ↓
2. Router selects candidate models (by tier/priority)
   ↓
3. FOR EACH candidate model:
   ↓
   ├─→ Check throttle ban (existing)
   ├─→ Check exhaustion timestamp (existing)
   ├─→ **NEW: Check rate limiter**
   │    ├─ Get current usage (RPM, TPM, RPD, TPD)
   │    ├─ Compare to tier-specific limits
   │    ├─ Apply 95% safety margin
   │    ├─ Project estimated tokens
   │    └─ SKIP if would exceed → record metric
   ↓
4. Make API call to selected model
   ↓
5. **NEW: Record actual tokens to rate limiter**
   ↓
6. Update legacy StateManager counters (compatibility)
```

### Before vs After

#### **BEFORE** (Reactive):
1. Make API call
2. Receive 429 error
3. Throttle manager bans model for 2 minutes
4. Retry with next model
5. **Problem**: Wasted API call, increased latency, quota consumption

#### **AFTER** (Proactive):
1. Check rate limiter **before** API call
2. Skip model if limits would be exceeded
3. Try next model immediately
4. **Benefit**: No wasted calls, faster failover, better quota management

## Configuration

### Model Config Structure (`models_config.json`)

Each model has tier-specific limits:

```json
{
  "models": {
    "deepseek-chat": {
      "limits": {
        "requests_per_minute": 60,
        "requests_per_day": 10000,
        "tokens_per_minute": 500000
      },
      "free_tier_limits": {
        "requests_per_day": 1000,
        "requests_per_minute": 30,
        "tokens_per_minute": 200000,
        "tokens_per_day": 1000000
      },
      "paid_tier_limits": {
        "requests_per_day": 10000,
        "requests_per_minute": 60,
        "tokens_per_minute": 500000,
        "tokens_per_day": 5000000
      }
    }
  }
}
```

### Rate Limiter Configuration

**Safety Margin** (default 95%):
```python
rate_limiter = get_rate_limiter(safety_margin=0.95)  # Use 95% of limits
```

**Why 95%?** Prevents race conditions where multiple concurrent requests push usage over limit between check and API call.

**Adjustable**: Can be set to 0.90 (90%), 0.98 (98%), etc. based on concurrency patterns.

## Monitoring & Debugging

### Log Messages

#### Preemptive Skip (Model blocked before API call):
```
WARNING: Model deepseek-chat rate limit check failed for free tier: RPM limit: 30/30 | 
Current usage: RPM=30/30, TPM=150000/200000, RPD=500/1000
```

#### Rate Limit Check Passed:
```
DEBUG: Model deepseek-chat rate limit check passed | 
Usage: RPM=25/30, TPM=120000/200000
```

#### 429 Error (Reactive fallback):
```
ERROR: Model gemini-2.5-flash-lite hit rate limit (429): tokens_per_minute | 
Error: Resource exhausted | 
Current usage: RPM=15, TPM=250000, RPD=100, TPD=500000
```

### Metrics Events

**Tracked in `data/metrics/metrics.jsonl`**:

1. **`rate_limit_preemptive_skip`**:
   ```json
   {
     "type": "rate_limit_preemptive_skip",
     "timestamp": 1702567890,
     "model_id": "deepseek-chat",
     "tier": "free",
     "reason": "RPM limit: 30/30",
     "usage": {"requests_last_minute": 30, "tokens_last_minute": 150000, ...}
   }
   ```

2. **`rate_limit_429_error`**:
   ```json
   {
     "type": "rate_limit_429_error",
     "timestamp": 1702567890,
     "model_id": "gemini-2.5-flash-lite",
     "limit_type": "tokens_per_minute",
     "error_message": "Resource exhausted",
     "usage": {"requests_last_minute": 15, "tokens_last_minute": 250000, ...}
   }
   ```

### Dashboard Visibility

**Recommended Dashboard Cards** (to be added):

1. **Rate Limit Prevention Rate**:
   - `preemptive_skips / (preemptive_skips + 429_errors)`
   - Target: >90% (most throttling prevented before API call)

2. **Model Usage by Limit Type**:
   - Bar chart: RPM, TPM, RPD, TPD usage by model
   - Shows which limits are constraining

3. **429 Error Trend**:
   - Should **decrease** after implementation
   - Remaining 429s indicate limits need tuning

## Benefits

### 1. **Reduced 429 Errors**
- Preemptively skip models that would be throttled
- Fallback to next model without wasted API call

### 2. **Faster Failover**
- No need to wait for 429 response + retry delay
- Immediate selection of alternative model

### 3. **Better Quota Management**
- Accurate tracking prevents exceeding provider limits
- Daily reset ensures fresh start each day
- Per-tier limits prevent free tier abuse

### 4. **Improved Visibility**
- Detailed logging of rate limit decisions
- Metrics for monitoring and tuning
- Clear distinction between limit types (RPM vs TPM vs daily)

### 5. **Cost Optimization**
- No wasted API calls on throttled models
- Better distribution across available models
- Prevents quota exhaustion lockouts

## Known Limitations & Future Enhancements

### Current Limitations

1. **Token Estimation**:
   - Uses rough estimate: `len(prompt.split()) * 2`
   - Could be more accurate with tiktoken library

2. **Per-Session Limits**:
   - Currently global per model
   - Single session can consume entire model quota
   - **Future**: Add per-session rate limiting

3. **Burst Tolerance**:
   - Uses sliding window (strict enforcement)
   - **Alternative**: Token bucket algorithm allows controlled bursts

4. **Rate Limit Reset Timing**:
   - Daily reset at midnight UTC
   - Providers may use rolling 24-hour windows
   - **Future**: Make reset strategy configurable

### Recommended Enhancements

1. **Token Counting Library**:
   ```python
   import tiktoken
   encoding = tiktoken.encoding_for_model(model_id)
   estimated_tokens = len(encoding.encode(prompt))
   ```

2. **Per-Session Quotas**:
   ```python
   session_limits = {
       'free': {'rpm': 5, 'tpm': 10000},
       'paid': {'rpm': 20, 'tpm': 50000}
   }
   ```

3. **Adaptive Safety Margin**:
   - Increase margin during high concurrency
   - Decrease during low traffic for better utilization

4. **Rate Limit Prediction API**:
   ```python
   time_until_available = rate_limiter.predict_availability(model_id, estimated_tokens)
   # "Model available in 45 seconds"
   ```

## Testing

### Unit Tests

**Run**: `python3 -m pytest tests/test_rate_limiter.py -v`

**Coverage**:
- RateLimitWindow: 5 tests
- RateLimiter: 7 tests
- Concurrent access: 1 test
- **Total**: 13/13 passing ✅

### Integration Testing

**Manual Test Script**:
```python
import asyncio
from sentinelrouter.sentinelrouter.rate_limiter import get_rate_limiter

async def test():
    limiter = get_rate_limiter()
    
    # Simulate 35 requests in quick succession
    for i in range(35):
        await limiter.record_request("deepseek-chat", tokens=5000)
    
    # Check if 36th request would be blocked (RPM limit: 30)
    allowed, reason, usage = await limiter.check_rate_limits(
        "deepseek-chat",
        rpm_limit=30,
        tpm_limit=200000
    )
    
    print(f"Allowed: {allowed}, Reason: {reason}")
    print(f"Usage: {usage}")

asyncio.run(test())
```

## Deployment Checklist

- [x] Rate limiter module created
- [x] Router logic integration complete
- [x] Server lifecycle hooks added
- [x] Metrics tracking implemented
- [x] Unit tests written and passing
- [x] Docker image rebuilt
- [x] Server restarted with new code
- [ ] Monitor logs for rate limit messages
- [ ] Verify 429 errors decrease
- [ ] Add dashboard cards for rate limit metrics
- [ ] Tune safety margin based on traffic patterns

## Files Modified

1. **New Files**:
   - `sentinelrouter/sentinelrouter/rate_limiter.py` (313 lines)
   - `tests/test_rate_limiter.py` (267 lines)

2. **Modified Files**:
   - `sentinelrouter/sentinelrouter/router_logic.py` (+60 lines)
   - `sentinelrouter/sentinelrouter/server.py` (+12 lines)
   - `sentinelrouter/sentinelrouter/metrics.py` (+45 lines)

3. **Total Changes**:
   - Lines added: ~697
   - Lines modified: ~100
   - Files changed: 5

## Git Commit Message

```
feat: implement sliding window rate limiting with preemptive throttling prevention

- Add RateLimiter class with time-windowed RPM/TPM/RPD/TPD tracking
- Integrate preemptive rate limit checks in router model selection
- Record actual token usage for accurate sliding window calculations
- Add daily counter reset at midnight UTC via background task
- Enhance 429 error logging with rate limit type detection
- Add rate limit metrics (preemptive_skip, 429_error) for dashboard
- Implement 95% safety margin to prevent concurrent request race conditions
- Add comprehensive unit tests (13/13 passing)

Benefits:
- Reduces 429 errors by skipping throttled models before API call
- Improves failover latency (no retry delay)
- Better quota management with accurate time-windowed tracking
- Enhanced visibility with detailed logs and metrics

Resolves: Rate limiting verification and enhancement task
```

## Support & Troubleshooting

### Issue: Rate limiter not preventing 429s

**Check**:
1. Verify safety margin isn't too high: `get_rate_limiter(safety_margin=0.95)`
2. Check if limits in `models_config.json` match provider limits
3. Look for "rate limit check passed" logs - usage should be near limit
4. Confirm token estimation is reasonable (2 tokens/word average)

### Issue: Models being skipped too aggressively

**Fix**:
- Lower safety margin: `get_rate_limiter(safety_margin=0.90)`
- Increase limits in `models_config.json` if provider allows
- Check if multiple sessions sharing same model quota

### Issue: Daily counters not resetting

**Check**:
1. Verify rate limiter background task started: Look for "Rate limiter started" log
2. Check server uptime - must run through midnight UTC
3. Manually trigger reset: `rate_limiter.reset_all_daily_counters()`

---

**Implementation Date**: December 14, 2025  
**Version**: 1.0.0  
**Status**: ✅ Deployed and Running
