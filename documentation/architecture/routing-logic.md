# Routing Logic

The routing logic is the core intelligence of SentinelRouter, responsible for deciding which LLM model (weak or strong) should handle each request. It integrates four independent modules (A‑D) with a unified configuration system, semantic caching, and real‑time state management.

## Overview

Every request passes through a deterministic pipeline that:

1. **Checks the session budget** (Module A – Budget Kill‑Switch).
2. **Detects conversational cycles** (Module D – Cycle Detection).
3. **Evaluates prompt complexity** (Module B – Stingy Judge), unless skipped or deferred.
4. **Applies dynamic thresholds** (Module C – Dynamic Thresholding) to decide between weak and strong models.
5. **Selects a concrete model** from the active pool, respecting rate limits, throttling, and failover order.
6. **Calls the LLM**, records the outcome, updates all tracking systems, and returns the response.

The entire flow is designed to maximize cost efficiency while maintaining response quality and avoiding repetitive or stuck conversations.

## Architectural Diagram

```mermaid
graph TD
    A[Request arrives] --> B[Budget Check (Module A)]
    B --> C[Cycle Detection (Module D)]
    C --> D{Judge Needed?}
    D -->|Yes| E[Call Judge (Module B)]
    D -->|No| F[Use default complexity]
    E --> G[Apply Dynamic Threshold (Module C)]
    F --> G
    G --> H{Decision: weak or strong?}
    H -->|weak| I[Select weak‑tier model]
    H -->|strong| J[Select strong‑tier model]
    I --> K[Check rate limits & throttling]
    J --> K
    K --> L[Call LLM with failover]
    L --> M[Update budget, state, cache, cycle detector]
    M --> N[Return response]
```

## The Four Modules

### Module A: Budget Kill‑Switch

**Purpose:** Prevent a single session from exceeding a predefined cost limit.

**Implementation:** `sentinelrouter/sentinelrouter/budget.py`

- Each session has a `max_cost_per_session` (default $25.00).
- Before any LLM call, the router estimates a worst‑case cost (using the most expensive model) and checks whether adding that cost would exceed the limit.
- If the limit would be exceeded, the request is rejected with a clear error.
- After a successful call, the actual cost is added to the session’s running total.

**Configuration:**

- `MAX_COST_PER_SESSION` environment variable (default 25.0).
- Can be overridden per session via the `X‑Session‑Tier` header (paid tier may have a higher limit).

### Module B: Stingy Judge

**Purpose:** Classify the prompt’s complexity and impact scope to decide whether a strong model is justified.

**Implementation:** `sentinelrouter/sentinelrouter/judge.py`

The judge uses a Gemini‑based model (Gemini 2.5 Flash Lite as primary, with DeepSeek and other Gemini models as backups) to analyze the prompt and return:

- **Complexity score** (0.0–1.0): Higher values indicate the prompt is more complex.
- **Impact scope** (`LOW`, `MEDIUM`, `HIGH`): How critical the response is.
- **Reasoning** (text): A short explanation of the classification.

The judge can be used in three modes, controlled by the `use_judge` parameter:

| Mode | `use_judge` value | Behavior |
|------|-------------------|----------|
| **Always** | `true` | Judge is called for every request. |
| **Never** | `false` | Judge is skipped; the request is treated as low‑complexity (weak model). |
| **Conditional (smart)** | `null` (default) | Judge is skipped initially. If the weak‑model call takes longer than 15 seconds, the judge is called and may trigger an escalation to a strong model. |

**Configuration:**

- Judge models are defined in `models_config.json` under `judge_config.model_order`.
- The primary judge is `gemini‑2.5‑flash‑lite‑primary` (free tier).
- Backup judges are `deepseek‑judge‑backup1` and other Gemini models.

### Module C: Dynamic Thresholding

**Purpose:** Automatically adjust the complexity threshold that triggers escalation to a strong model, aiming to keep the overall escalation rate at a target (default 5 %).

**Implementation:** `sentinelrouter/sentinelrouter/threshold.py`

- Maintains a rolling window of recent routing decisions.
- Computes the current escalation rate (percentage of requests that were routed to strong models).
- If the escalation rate exceeds the target, **strict mode** is activated, making it harder to escalate.
- In strict mode:
  - A penalty of 0.15 is subtracted from the complexity score.
  - Only prompts with `HIGH` impact scope are allowed to escalate.
- The threshold itself can be adjusted up or down based on the observed escalation rate.

**Configuration:**

- `TARGET_ESCALATION_RATE` environment variable (default 0.05 = 5 %).
- `ROLLING_WINDOW_SIZE` (default 20) – number of recent decisions considered.

### Module D: Cycle Detection

**Purpose:** Detect when a conversation is stuck in a loop (same or similar prompts being repeated) and force escalation to a strong model to break the cycle.

**Implementation:** `sentinelrouter/sentinelrouter/cycle_detector.py`

- Uses SimHash (similarity hashing) to compare the current prompt with recent prompts in the same session.
- If a close match is found, a cycle is flagged and the request is **automatically routed to a strong model**, overriding the judge’s recommendation.
- The detector maintains a per‑session FIFO queue of recent prompt‑response pairs.

**Configuration:**

- Similarity threshold (currently hard‑coded) can be adjusted in `cycle_detector.py`.

## Step‑by‑Step Flow

### 1. Request Arrival

The router receives a request with:

- `session_id` (or generated from client IP)
- `prompt` (text)
- `messages` (list of message objects)
- Optional headers: `X‑Use‑Judge`, `X‑Session‑Tier`

### 2. Semantic Cache Lookup

Before any module runs, the router computes a semantic hash of the prompt and message context and checks the semantic cache (`sentinelrouter/sentinelrouter/semantic_cache.py`).

- If the same (or similar) prompt has been seen before and the cache has **confident history** (e.g., 3+ previous calls with consistent routing), the router may skip the judge and use the cached recommendation.
- Cache confidence is based on the ratio of weak vs. strong calls in the history.

### 3. Budget Check

Calls `BudgetKillSwitch.check_budget()` with a worst‑case cost estimate. If the session would exceed its limit, the request is rejected.

### 4. Cycle Detection

`CycleDetector.detect_cycle_with_prompt()` is called. If a cycle is detected, the decision is forced to **strong** and the rest of the judge/threshold logic is skipped for this step (but the judge may still be called later for logging).

### 5. Judge Invocation

Based on `use_judge` and cache confidence:

- **Cache‑confident skip**: If the cache indicates a clear preference (e.g., 80 % of previous calls used weak models), the judge is skipped and the cached recommendation is used.
- **Explicit skip** (`use_judge=false`): Judge is skipped, complexity score = 0.0, impact = `LOW`.
- **Always judge** (`use_judge=true`): The judge is called, returning complexity, impact, and reasoning.
- **Conditional mode** (`use_judge=null`): Judge is deferred. The router will attempt the weak model first; if the call takes longer than 15 seconds, the judge is called and may escalate.

### 6. Threshold Application

The current threshold is obtained from `DynamicThreshold.get_threshold()`. If strict mode is active (escalation rate > target), a penalty is applied.

The routing decision is made by `_decide_route()`:

```python
if cycle_detected:
    return "strong"
if strict_mode:
    effective_score = complexity_score - 0.15
    if effective_score < threshold:
        return "weak"
    if impact_scope != "HIGH":
        return "weak"
    return "strong"
else:
    return "strong" if complexity_score >= threshold else "weak"
```

### 7. Model Selection

Once the tier (`weak`/`strong`) is decided, the router queries the StateManager for active models in that priority group.

- The StateManager returns models sorted by `routing.order`.
- The router iterates through the list, checking:
  - Throttle bans (recent errors)
  - Rate‑limit exhaustion (daily, RPM)
  - Tier‑specific limits (`free_tier_limits` vs `paid_tier_limits`)
- The first model that passes all checks is selected.

### 8. LLM Call with Failover

The router calls the selected model’s client (`chat_completion`). If the call fails (network error, rate limit, etc.), the router:

1. Records the error and may ban the model temporarily via the throttle manager.
2. Falls back to the next model in the same priority group.
3. If all models in the group fail, the request fails.

In conditional mode, a timeout of 15 seconds is enforced for weak‑model calls. If the timeout is reached, the judge is called and may trigger an escalation to the strong tier.

### 9. Post‑Call Updates

After a successful LLM call:

- **Budget**: The actual cost is added to the session.
- **StateManager**: The model’s `requests_today`, `tokens_today`, `total_cost_session`, and `current_rpm` are updated.
- **Cycle detector**: The prompt‑response pair is added to the session’s history.
- **Dynamic threshold**: The decision (weak/strong) is recorded, and the threshold may be adjusted.
- **Semantic cache**: The interaction is recorded, building history for future cache‑based routing.
- **Audit log**: Full request/response details are written to the database and log file.

### 10. Response

The router returns a dictionary containing:

- `model_used`: The model ID that handled the request.
- `response`: The LLMResponse object (content, model, usage, cost).
- `complexity_score`, `impact_scope`, `reasoning`: From the judge (or defaults).
- `decision_reason`: Human‑readable explanation of the routing decision.
- `session_cost`: The session’s cumulative cost after this request.
- `cycle_detected`: Boolean.
- `tier`: The tier that was used (`weak`/`strong`).
- `use_judge`: Whether the judge was invoked.

## Configuration and Tuning

### Environment Variables

| Variable | Default | Effect on Routing |
|----------|---------|-------------------|
| `USE_JUDGE` | `null` (smart) | Global default for judge usage. |
| `COMPLEXITY_THRESHOLD` | 0.5 | Initial threshold for escalation. |
| `TARGET_ESCALATION_RATE` | 0.05 | Target escalation rate (5 %) for dynamic thresholding. |
| `ROLLING_WINDOW_SIZE` | 20 | Number of recent decisions considered for threshold adjustment. |
| `ENABLE_CYCLE_DETECTION` | `true` | Enable/disable Module D. |
| `ENABLE_DYNAMIC_THRESHOLD` | `true` | Enable/disable Module C. |

### Model‑Specific Configuration

Each model’s routing behavior is defined in `models_config.json`:

```json
"deepseek-chat": {
  "routing": {
    "priority_group": "fast_tier",
    "order": 1
  },
  "limits": { ... },
  "free_tier_limits": { ... },
  "paid_tier_limits": { ... }
}
```

- `priority_group`: `"fast_tier"` (weak) or `"strong_tier"` (strong).
- `order`: Lower numbers are tried first within the same priority group.

### Session‑Level Overrides

Clients can influence routing via HTTP headers:

- `X-Use-Judge`: `true`, `false`, or `smart` (maps to `null`).
- `X-Session-Tier`: `free` or `paid` (affects which rate‑limit set is applied).

## Debugging and Monitoring

### Dashboard

The SentinelRouter dashboard (`http://localhost:8001`) provides real‑time visibility into routing decisions:

- **Live Traffic tab**: Shows current RPM, session costs, and active models.
- **Router Logic tab**: Displays the last 50 routing decisions with complexity scores, thresholds, and decision reasons.
- **Configuration tab**: Allows on‑the‑fly adjustment of model priorities and rate limits.

### Logs

The router logs each decision at `INFO` level. Example:

```
[2025‑12‑14 10:42:56] Routing decision: STRONG tier | complexity=0.873, threshold=0.721, impact=HIGH, strict_mode=False, cycle_detected=False | Reason: complexity_score 0.873 >= threshold 0.721; impact_scope HIGH
```

### Metrics

Prometheus‑format metrics are exposed at `/dashboard/api/v1/metrics`:

- `sentinelrouter_routing_decisions_total`: Counter of weak/strong decisions.
- `sentinelrouter_judge_invocations_total`: Number of judge calls.
- `sentinelrouter_cycle_detections_total`: Number of cycles detected.
- `sentinelrouter_model_latency_seconds`: Histogram of LLM call latencies.

## Common Scenarios

### 1. Simple Prompts

- Prompt: “What is 5 + 3?”
- Cache: No confident history.
- Judge: Skipped (conditional mode).
- Complexity: 0.0 (default).
- Threshold: 0.5 → decision = weak.
- Model: DeepSeek Chat (fast_tier, order 1).
- Outcome: Fast, cheap response.

### 2. Complex Reasoning

- Prompt: “Explain the quantum Hall effect in simple terms.”
- Cache: No history.
- Judge: Called, returns complexity 0.85, impact HIGH.
- Threshold: 0.6 → decision = strong.
- Model: Claude Opus 4 (strong_tier, order 1).
- Outcome: High‑quality, more expensive response.

### 3. Conversation Loop

- Previous three prompts are variations of “Tell me a joke.”
- Cycle detector flags a cycle (SimHash similarity > 90 %).
- Decision: forced to strong.
- Model: Claude Opus 4.
- Outcome: Breaks the loop with a different style of response.

### 4. Budget Exceeded

- Session has already spent $24.90, limit $25.00.
- Worst‑case estimate for next call: $5.00.
- Budget check fails → request rejected with error.

## Extending the Router

To add a new routing criterion (e.g., time‑of‑day based routing):

1. Create a new module (e.g., `time_router.py`) that returns a recommendation.
2. Inject it into the `Router` class, similar to how the judge is injected.
3. Call it at the appropriate step in `route()` and incorporate its output into `_decide_route()`.

The modular design makes it straightforward to plug in additional decision‑making components.

---

*Last updated: 2025‑12‑14*  
*See also: [Configuration Guide](../getting-started/configuration.md), [Judge System](judge-system.md), [Semantic Cache](semantic-cache.md)*