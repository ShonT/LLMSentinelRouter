# Model Resolution Architecture & OOP Improvements

## Table of Contents
1. [Current Architecture Analysis](#current-architecture)
2. [OOP Design Patterns Discussion](#oop-improvements)
3. [Backup Weak Models Implementation](#backup-models-feature)
4. [Migration Guide](#migration-guide)
5. [Testing Strategy](#testing-strategy)

---

## Current Architecture

### How Model Resolution Works

The current system uses a **hardcoded binary routing** approach:

```
┌─────────────┐
│   Request   │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│  Router Decision Logic              │
│  - Budget check                     │
│  - Cycle detection                  │
│  - Judge (complexity scoring)       │
│  - Dynamic thresholding             │
└──────┬──────────────────────────────┘
       │
       ▼
    Decision: "weak" or "strong"
       │
       ├─────────────┬─────────────┐
       ▼             ▼             ▼
  if "weak"     if "strong"    (fallback)
       │             │             │
       ▼             ▼             ▼
  DeepSeek      Anthropic     Opposite
   Client        Client        of choice
```

### Key Components

**1. Router (`router_logic.py`)**
- **Line 138-141**: Hardcoded model selection
  ```python
  if route_decision == "weak":
      client = await get_deepseek_client()
      model_used = "deepseek"
  ```

**2. Client Layer (`clients.py`)**
- **Lines 215-235**: Singleton pattern for clients
  ```python
  async def get_deepseek_client() -> DeepSeekClient:
      global _deepseek_client
      if _deepseek_client is None:
          _deepseek_client = DeepSeekClient()
      return _deepseek_client
  ```

**3. Fallback Logic (`router_logic.py`, Lines 147-157)**
- **Single attempt**: weak → strong OR strong → weak
- **No history tracking**: Doesn't remember which models failed
- **No circuit breaker**: Will keep retrying failed providers
- **No alternatives within tier**: Can't try backup weak model

### Problems with Current Design

| Issue | Impact | Example |
|-------|--------|---------|
| **Tight Coupling** | Can't add new providers easily | Want to add Groq as backup? Must modify Router code |
| **No Abstraction** | Clients tied to specific providers | `get_deepseek_client()` is a function, not a role |
| **Binary Decision** | Only 2 tiers: weak/strong | Can't have "medium" complexity tier |
| **No Failure Memory** | Repeats failed calls | If DeepSeek API is down, keeps trying it |
| **Single Fallback** | Limited resilience | Primary fails → try 1 backup → give up |

---

## OOP Improvements

### Design Patterns Applied

#### 1. **Registry Pattern** (Model Registry)

**Purpose**: Central catalog of available models

```python
# BEFORE (hardcoded):
client = await get_deepseek_client()

# AFTER (registry):
provider = registry.select_provider(ModelTier.WEAK)
response = await provider.chat_completion(messages)
```

**Benefits**:
- ✅ Single source of truth for all models
- ✅ Easy to add/remove providers at runtime
- ✅ Centralized configuration
- ✅ Supports multiple providers per tier

#### 2. **Strategy Pattern** (Provider Selection)

**Purpose**: Pluggable algorithms for choosing models

```python
class PriorityFailoverStrategy:
    """Try primary first, then backups in order."""
    
class RoundRobinStrategy:
    """Distribute load across providers."""
    
class LeastCostStrategy:
    """Choose cheapest available provider."""
```

**Benefits**:
- ✅ Can change selection algorithm without modifying Router
- ✅ A/B test different strategies
- ✅ Optimize for cost, latency, or reliability

#### 3. **Circuit Breaker Pattern** (Health Tracker)

**Purpose**: Prevent cascading failures

```python
class ProviderHealthTracker:
    def record_failure(self, provider_id: str):
        # After 3 failures in 5 minutes:
        # Open circuit → stop sending requests
        # Wait 60 seconds → try again
```

**Benefits**:
- ✅ Automatic failover to healthy providers
- ✅ Prevents wasting time on failing services
- ✅ Self-healing: tries again after cooldown
- ✅ Metrics for monitoring

#### 4. **Decorator Pattern** (Provider Wrapper)

**Purpose**: Add functionality without modifying clients

```python
class CachingProviderDecorator(ModelProvider):
    """Cache responses to reduce API calls."""

class MetricsProviderDecorator(ModelProvider):
    """Track latency, cost, token usage."""
    
class RetryProviderDecorator(ModelProvider):
    """Add retry logic to any provider."""
```

**Benefits**:
- ✅ Composable behavior
- ✅ Cross-cutting concerns (logging, metrics, caching)
- ✅ Doesn't modify underlying clients

### Class Diagram (Improved Architecture)

```
┌─────────────────────────────────────────┐
│           ModelRegistry                 │
│  - _providers: Dict[Tier, List]        │
│  - health_tracker: HealthTracker        │
│  + register_provider()                  │
│  + select_provider()                    │
│  + call_with_failover()                 │
└────────────┬────────────────────────────┘
             │
             │ manages
             ▼
┌─────────────────────────────────────────┐
│        ModelProvider (dataclass)        │
│  - provider_id: str                     │
│  - tier: ModelTier                      │
│  - client: BaseLLMClient                │
│  - priority: int                        │
│  + chat_completion()                    │
└────────────┬────────────────────────────┘
             │
             │ wraps
             ▼
┌─────────────────────────────────────────┐
│       BaseLLMClient (existing)          │
│  - api_key, base_url, model_id          │
│  + chat_completion()                    │
│  + _request_with_retry()                │
└─────────────────────────────────────────┘
      ▲                    ▲
      │                    │
      │                    │
┌─────┴─────┐      ┌──────┴──────┐
│ DeepSeek  │      │  Anthropic  │
│  Client   │      │   Client    │
└───────────┘      └─────────────┘
```

---

## Backup Weak Models Feature

### Requirements

**User Story**: 
> "If the last 3 calls to the primary weak model failed, automatically switch to a backup weak model (e.g., different endpoint or provider) to ensure weak model issues don't block the system."

### Implementation

**1. Register Multiple Weak Models**

```python
# In config or startup:
registry = ModelRegistry()

# Primary weak model (DeepSeek)
registry.register_provider(ModelProvider(
    provider_id="deepseek-primary",
    tier=ModelTier.WEAK,
    client=DeepSeekClient(api_key=DEEPSEEK_KEY),
    priority=0  # Highest priority
))

# Backup weak model #1 (DeepSeek alternate endpoint)
registry.register_provider(ModelProvider(
    provider_id="deepseek-backup",
    tier=ModelTier.WEAK,
    client=DeepSeekClient(
        api_key=DEEPSEEK_BACKUP_KEY,
        base_url="https://backup.deepseek.com"  # Different endpoint
    ),
    priority=1  # Second priority
))

# Backup weak model #2 (Different provider - Groq, Mistral, etc.)
registry.register_provider(ModelProvider(
    provider_id="groq-llama3",
    tier=ModelTier.WEAK,
    client=GroqClient(api_key=GROQ_KEY),
    priority=2  # Third priority
))
```

**2. Automatic Failover Logic**

The `ModelRegistry.call_with_failover()` method handles this automatically:

```python
async def call_with_failover(self, tier, messages, max_attempts=3):
    attempted_providers = []
    
    for attempt in range(max_attempts):
        # Select next available provider (skips failed ones)
        provider = self.select_provider(tier, exclude=attempted_providers)
        
        if provider is None:
            break  # No more providers to try
        
        try:
            response = await provider.chat_completion(messages)
            self.health_tracker.record_success(provider.provider_id)
            return response, provider.provider_id
        except LLMClientError as e:
            # Record failure, open circuit breaker if threshold hit
            self.health_tracker.record_failure(provider.provider_id)
            attempted_providers.append(provider.provider_id)
            continue  # Try next provider
    
    raise LLMClientError("All providers failed")
```

**3. Circuit Breaker Behavior**

```python
class ProviderHealthTracker:
    def record_failure(self, provider_id: str):
        # Track failure timestamp
        self.recent_failures[provider_id].append(datetime.utcnow())
        
        # If 3 failures in last 5 minutes:
        if self.get_recent_failure_count(provider_id) >= 3:
            # Open circuit for 60 seconds
            self.circuit_open_until[provider_id] = now + timedelta(seconds=60)
            logger.warning(f"Circuit OPEN for {provider_id}")
```

**Flow Example**:

```
Request 1: Try deepseek-primary → ✅ Success
Request 2: Try deepseek-primary → ✅ Success
Request 3: Try deepseek-primary → ❌ Fail (1st failure)
Request 4: Try deepseek-primary → ❌ Fail (2nd failure)
Request 5: Try deepseek-primary → ❌ Fail (3rd failure)
           → Circuit OPEN for deepseek-primary
           → Switch to deepseek-backup → ✅ Success
Request 6: Skip deepseek-primary (circuit open)
           → Try deepseek-backup → ✅ Success
...
After 60 seconds:
Request N: Circuit CLOSED for deepseek-primary
           → Try deepseek-primary again → ✅ Success (recovered!)
```

### Configuration

**Environment Variables**:

```bash
# .env
# Primary weak model
DEEPSEEK_API_KEY=sk-xxx
WEAK_MODEL_ID=deepseek-reasoner

# Backup weak model (optional)
DEEPSEEK_BACKUP_API_KEY=sk-yyy
DEEPSEEK_BACKUP_ENDPOINT=https://backup.deepseek.com

# Alternative weak model (optional)
GROQ_API_KEY=gsk-zzz
GROQ_MODEL_ID=llama-3.1-8b-instant

# Failover settings
FAILOVER_MAX_ATTEMPTS=3          # Try up to 3 providers
CIRCUIT_BREAKER_THRESHOLD=3      # Open circuit after 3 failures
CIRCUIT_BREAKER_COOLDOWN=60      # Wait 60s before retry
```

**Settings Class**:

```python
class Settings(BaseSettings):
    # ... existing settings ...
    
    # Backup weak model support
    deepseek_backup_api_key: Optional[str] = Field(None, env="DEEPSEEK_BACKUP_API_KEY")
    deepseek_backup_endpoint: Optional[str] = Field(None, env="DEEPSEEK_BACKUP_ENDPOINT")
    
    groq_api_key: Optional[str] = Field(None, env="GROQ_API_KEY")
    groq_model_id: str = Field("llama-3.1-8b-instant", env="GROQ_MODEL_ID")
    
    # Failover configuration
    failover_max_attempts: int = Field(3, env="FAILOVER_MAX_ATTEMPTS")
    circuit_breaker_threshold: int = Field(3, env="CIRCUIT_BREAKER_THRESHOLD")
    circuit_breaker_cooldown: int = Field(60, env="CIRCUIT_BREAKER_COOLDOWN")
```

---

## Migration Guide

### Phase 1: Add Model Registry (Non-Breaking)

**Step 1**: Add new files
- ✅ `model_registry.py` (created)
- ✅ `INTEGRATION_GUIDE.py` (created)

**Step 2**: Keep existing code working
```python
# In router_logic.py, add optional registry parameter
class Router:
    def __init__(self, db_session, model_registry: Optional[ModelRegistry] = None):
        self.db = db_session
        self.model_registry = model_registry  # New, optional
        # ... existing code ...
    
    async def route(self, ...):
        # If registry provided, use it; otherwise use old code
        if self.model_registry:
            return await self._route_with_registry(...)
        else:
            return await self._route_legacy(...)  # Original implementation
```

**Step 3**: Test in parallel
- Run unit tests with old path
- Add new tests for registry path
- Verify same behavior

### Phase 2: Gradual Rollout

**Step 1**: Enable registry for specific sessions
```python
# Feature flag approach
if session_id.startswith("test-") or settings.enable_model_registry:
    return await self._route_with_registry(...)
else:
    return await self._route_legacy(...)
```

**Step 2**: Monitor metrics
- Track success rates for both paths
- Compare costs, latency, error rates
- Monitor circuit breaker events

**Step 3**: Increase rollout percentage
```python
# Gradually increase from 1% → 10% → 50% → 100%
if hash(session_id) % 100 < settings.registry_rollout_percentage:
    return await self._route_with_registry(...)
```

### Phase 3: Full Migration

**Step 1**: Make registry required
```python
class Router:
    def __init__(self, db_session, model_registry: ModelRegistry):
        # No longer optional
```

**Step 2**: Remove old code
- Delete `_route_legacy()` method
- Remove `get_deepseek_client()` / `get_anthropic_client()` functions
- Clean up unused imports

**Step 3**: Update tests
- Rewrite tests to use registry
- Add tests for backup failover
- Test circuit breaker scenarios

---

## Testing Strategy

### Unit Tests

**Test 1: Provider Registration**
```python
def test_register_multiple_weak_models():
    registry = ModelRegistry()
    
    # Register 3 weak models with different priorities
    registry.register_provider(ModelProvider(
        provider_id="weak-1", tier=ModelTier.WEAK, 
        client=MockClient(), priority=0
    ))
    registry.register_provider(ModelProvider(
        provider_id="weak-2", tier=ModelTier.WEAK,
        client=MockClient(), priority=1
    ))
    
    # Verify priority ordering
    providers = registry.get_available_providers(ModelTier.WEAK)
    assert providers[0].provider_id == "weak-1"
    assert providers[1].provider_id == "weak-2"
```

**Test 2: Circuit Breaker**
```python
async def test_circuit_breaker_opens_after_failures():
    tracker = ProviderHealthTracker(failure_threshold=3, cooldown_seconds=60)
    
    # Record 3 failures
    tracker.record_failure("provider-1")
    tracker.record_failure("provider-1")
    tracker.record_failure("provider-1")
    
    # Circuit should be open
    assert tracker.is_available("provider-1") == False
    
    # After cooldown, circuit closes
    await asyncio.sleep(61)
    assert tracker.is_available("provider-1") == True
```

**Test 3: Automatic Failover**
```python
async def test_failover_to_backup_on_failure():
    registry = ModelRegistry()
    
    # Primary fails, backup succeeds
    failing_client = MockClient(should_fail=True)
    backup_client = MockClient(should_fail=False)
    
    registry.register_provider(ModelProvider(
        provider_id="primary", tier=ModelTier.WEAK,
        client=failing_client, priority=0
    ))
    registry.register_provider(ModelProvider(
        provider_id="backup", tier=ModelTier.WEAK,
        client=backup_client, priority=1
    ))
    
    # Should automatically failover to backup
    response, provider_id = await registry.call_with_failover(
        ModelTier.WEAK, messages=[...]
    )
    
    assert provider_id == "backup"
    assert failing_client.call_count == 1
    assert backup_client.call_count == 1
```

### Integration Tests

**Test 4: End-to-End Failover**
```python
async def test_router_uses_backup_weak_model():
    """Test that router automatically fails over to backup weak model."""
    
    # Setup: Primary DeepSeek returns 500 error
    mock_deepseek_primary = setup_failing_mock()
    mock_deepseek_backup = setup_working_mock()
    
    # Make request
    response = await client.post("/v1/chat/completions", json={
        "messages": [{"role": "user", "content": "test"}],
        "session_id": "test-failover"
    })
    
    # Verify backup was used
    assert response.headers["X-Sentinel-Model-Used"] == "deepseek-backup"
    assert response.status_code == 200
```

**Test 5: Circuit Breaker Recovery**
```python
async def test_circuit_breaker_recovers_after_cooldown():
    """Test that circuit breaker reopens after cooldown period."""
    
    # Cause 3 failures to open circuit
    for i in range(3):
        await make_request_that_fails()
    
    # Verify circuit is open (uses backup)
    response1 = await make_request()
    assert response1.headers["X-Sentinel-Model-Used"] == "deepseek-backup"
    
    # Wait for cooldown
    await asyncio.sleep(61)
    
    # Fix the primary provider
    fix_primary_provider()
    
    # Verify circuit closed (uses primary again)
    response2 = await make_request()
    assert response2.headers["X-Sentinel-Model-Used"] == "deepseek-primary"
```

### Load Tests

**Test 6: Concurrent Failover**
```python
async def test_concurrent_requests_during_failover():
    """Ensure thread-safety during provider failover."""
    
    # Simulate primary becoming unavailable during load
    async def make_requests():
        tasks = [make_request() for _ in range(100)]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        return responses
    
    # Start load, then fail primary midway
    task = asyncio.create_task(make_requests())
    await asyncio.sleep(0.5)
    fail_primary_provider()
    
    responses = await task
    
    # All requests should succeed (failed over to backup)
    assert all(r.status_code == 200 for r in responses if not isinstance(r, Exception))
```

---

## Monitoring & Observability

### Metrics to Track

```python
# Add to Prometheus metrics or logging
metrics = {
    "provider_calls_total": Counter("calls per provider"),
    "provider_failures_total": Counter("failures per provider"),
    "provider_latency_seconds": Histogram("latency per provider"),
    "circuit_breaker_opens_total": Counter("circuit breaker events"),
    "failover_events_total": Counter("automatic failovers"),
    "provider_cost_usd": Counter("cost per provider"),
}
```

### Health Check Endpoint

```python
@app.get("/health/providers")
async def get_provider_health():
    """Get health status of all registered providers."""
    registry = get_model_registry()
    return registry.get_registry_status()

# Example response:
{
    "weak": [
        {
            "provider_id": "deepseek-primary",
            "available": true,
            "circuit_open": false,
            "failure_count": 0,
            "recent_failures": 0,
            "last_success": "2025-12-11T10:00:00Z"
        },
        {
            "provider_id": "deepseek-backup",
            "available": false,
            "circuit_open": true,
            "circuit_open_until": "2025-12-11T10:05:00Z",
            "failure_count": 5,
            "recent_failures": 3
        }
    ],
    "strong": [...]
}
```

---

## Summary

### Current Issues
- ❌ Hardcoded model selection
- ❌ No backup providers
- ❌ Single fallback attempt
- ❌ No failure tracking

### Improvements
- ✅ **Registry Pattern**: Central model catalog
- ✅ **Circuit Breaker**: Automatic failure detection
- ✅ **Priority Failover**: Try backups in order
- ✅ **Health Tracking**: Monitor provider status
- ✅ **Self-Healing**: Retry after cooldown

### Implementation
- ✅ Created `model_registry.py` with full implementation
- ✅ Created `INTEGRATION_GUIDE.py` with usage examples
- ✅ Non-breaking migration path
- ✅ Comprehensive testing strategy

### Next Steps
1. **Phase 1**: Add model_registry.py to codebase
2. **Phase 2**: Update Router to optionally use registry
3. **Phase 3**: Add configuration for backup models
4. **Phase 4**: Write unit tests for registry
5. **Phase 5**: Gradual rollout with monitoring
6. **Phase 6**: Full migration and cleanup
