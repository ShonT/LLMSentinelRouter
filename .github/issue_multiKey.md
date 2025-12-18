# Issue: Multi‑Key Support with Per‑Key Rate Limiting

## 1. Current State of RPD and RPM Throttling

### Rate Limiting Implementation
- **Location**: `sentinelrouter/sentinelrouter/rate_limiter.py`
- **Current Behavior**:
  - The `RateLimiter` class tracks requests and tokens per **model** (by `model_id`).
  - Uses sliding‑window counters for **requests per minute (RPM)**, **tokens per minute (TPM)**, **requests per day (RPD)**, and **tokens per day (TPD)**.
  - Limits are defined in each model’s `limits` and `free_tier_limits`/`paid_tier_limits` in `config/models_config.json`.
  - A safety margin (default 95%) is applied to enforce soft limits before hitting the hard provider limits.
- **Throttling Decision**:
  - `check_rate_limits()` returns `(allowed, reason, usage)` based on the model‑level counters.
  - If a model exceeds its limit, the entire model is considered “exhausted” until the window rolls over.
- **Limitations**:
  - No distinction between different API keys for the same model.
  - If one key is exhausted, the whole model is considered exhausted even if other keys are available.
  - Cannot set different rate limits per key (e.g., different RPM for different API keys of the same provider).

## 2. Changes Required to Store Multiple Keys per Model

### Configuration Schema (`sentinelrouter/schemas/config_models.py`)
- **Add a `keys` field** to `ModelConfig`:
  ```python
  class ModelKeyConfig(BaseModel):
      key_value: str = Field(..., description="API key (or env‑var reference)")
      display_name: Optional[str] = None
      limits: Optional[RateLimits] = None   # key‑specific limits, overrides model‑level
      priority: int = 0                     # 0 = primary, 1 = first backup, etc.
      status: Literal["ACTIVE", "DISABLED", "EXHAUSTED"] = "ACTIVE"

  class ModelConfig(BaseModel):
      # existing fields ...
      keys: List[ModelKeyConfig] = Field(default_factory=list)
  ```
- **Backward Compatibility**:
  - Keep the existing `model_key` field as a fallback.
  - If `keys` is empty, treat `model_key` as a single key with priority 0.
  - Migration script to convert existing config: each model’s `model_key` becomes the first entry in `keys`.

### Model Registry (`sentinelrouter/sentinelrouter/model_registry.py`)
- **Extend `ModelProvider`** to hold multiple keys and their priorities.
- **Modify `ProviderHealthTracker`** to track health per key (not just per provider).
- **Update `select_provider` logic** to iterate over keys in priority order, checking key‑specific rate limits and availability.

### Client Initialization (`sentinelrouter/sentinelrouter/clients.py`)
- For each key, create a separate client instance (or a client that can switch keys dynamically).
- The client must be able to use the key‑specific authentication header.

## 3. Changes Required to Allow Throttling or Banning Model*Key Pair

### Rate Limiter Changes (`rate_limiter.py`)
- **Key‑Level Tracking**:
  - Change `RateLimitWindow` to be identified by `(model_id, key_id)` where `key_id` is a hash of the key value or a unique identifier.
  - `RateLimiter.windows` should be a dict keyed by `(model_id, key_id)`.
- **Key‑Specific Limits**:
  - `check_rate_limits` should accept an optional `key_id` and use key‑specific limits if provided, otherwise fall back to model‑level limits.
- **Banning/Throttling**:
  - Add a `ban_key(model_id, key_id, until)` method to mark a key as banned (circuit‑breaker pattern).
  - Integrate with `ProviderHealthTracker` to track failures per key and open circuit breakers per key.

### Configuration and State Persistence
- **Key Status**:
  - The `status` field in `ModelKeyConfig` can be updated dynamically (e.g., mark as `EXHAUSTED` when daily limit is reached).
  - State should be persisted (via `state_manager.py`) so that bans/throttles survive restarts.

### Routing Logic (`router_logic.py`)
- When selecting a model for a request, iterate over its keys in priority order:
  1. Skip keys with status `DISABLED` or `EXHAUSTED`.
  2. Check key‑specific rate limits (via rate limiter).
  3. Check key health (circuit breaker).
  4. Use the first available key.
- If a key fails (rate limit, network error, etc.), mark it as temporarily unavailable and try the next key.

## 4. Testing – What Tests Need to be Modified

### Unit Tests
- **`tests/test_rate_limiter.py`**:
  - Add tests for key‑level rate‑limit windows.
  - Test that model‑level limits are used as fallback when key‑level limits are absent.
  - Test concurrent access with multiple keys.
- **`tests/unit/test_model_registry.py`** (if exists) or create new:
  - Test that `ModelProvider` correctly iterates over keys by priority.
  - Test failover behavior when primary key is exhausted.
- **`tests/unit/test_clients.py`**:
  - Verify that clients can be initialized with different keys and that requests use the correct key.
- **`tests/unit/test_router_logic.py`**:
  - Test routing decisions with multiple keys (preference order, fallback, etc.).

### Integration Tests
- **`tests/integ/`**:
  - Add a test that simulates a real scenario: primary key hits RPM limit, router automatically switches to backup key.
  - Test that bans/throttles are respected across requests.

### Configuration Tests
- **`tests/unit/test_config_models.py`**:
  - Validate that the new `keys` schema works and that backward compatibility is preserved.

## 5. Suggested Verification Methods

### 1. Manual Verification
- **Configuration Loading**:
  - Start the server with a modified `models_config.json` that contains multiple keys for one model.
  - Verify the configuration is loaded without errors (check logs).
- **Key Selection**:
  - Make a series of requests that would exceed the primary key’s RPM limit.
  - Observe in logs that the backup key is used for subsequent requests.
- **Banning**:
  - Manually ban a key (via admin API or by simulating failures) and confirm that requests are routed to the next key.

### 2. Automated Verification Script
- Create a script (`scripts/verify_multi_key.py`) that:
  - Sets up a test configuration with two keys for the same model.
  - Sends requests until the primary key’s limit is reached.
  - Asserts that the backup key is used.
  - Also verifies that key‑specific bans are honored.

### 3. Dashboard Monitoring
- Extend the dashboard (`sentinelrouter/sentinelrouter/dashboard.py`) to show per‑key usage and status.
- Verify that the dashboard correctly displays key‑level metrics (requests, tokens, limits, health).

### 4. Load Testing
- Use a load‑testing tool (e.g., locust) to simulate high traffic with multiple keys.
- Confirm that the rate limiter distributes load across keys according to their limits and that no single key exceeds its limits.

### 5. Backward Compatibility Check
- Run existing unit and integration tests to ensure no regression.
- Test with an old configuration (without `keys` field) to ensure it still works.

---

## Implementation Plan

1. **Update Schemas** (`config_models.py`) – add `ModelKeyConfig` and extend `ModelConfig`.
2. **Extend Rate Limiter** to track per‑key usage.
3. **Modify Model Registry** to support multiple keys and key‑level health tracking.
4. **Update Clients** to accept key‑specific configuration.
5. **Adjust Routing Logic** to iterate over keys.
6. **Write Migration Script** for existing configurations.
7. **Update Tests** and add new ones for the multi‑key functionality.
8. **Documentation** (update `documentation/architecture/rate-limiting-implementation.md` and `documentation/development/adding-new-models.md`).

## Estimated Effort
- **Small/Medium**: Core changes are localized to a few files, but careful integration is required to avoid breaking existing functionality.
- **Testing**: Significant test updates are needed to cover new scenarios.

## Priority
- **High**: This feature improves resilience and allows better utilization of provider quotas by distributing load across multiple keys.