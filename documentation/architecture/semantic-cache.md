# Semantic Cache

The semantic cache is a core component of SentinelRouter that records the history of similar requests and uses statistical confidence to influence routing decisions. It enables the router to learn from past interactions, reducing the need for redundant judge calls and improving latency by reusing successful routing patterns.

## Overview

The semantic cache:

- **Computes a semantic hash** of each prompt and its conversation context, capturing the meaning rather than exact wording.
- **Stores metadata** about each interaction: which model was used, latency, cost, tokens, judge invocation, complexity score, and impact scope.
- **Aggregates statistics** per hash to track the distribution of weak vs. strong model calls, average latency, total cost, etc.
- **Provides confidence‑based recommendations** – when a hash has enough samples and a clear preference (e.g., 80 % of previous calls used weak models), the cache can recommend a route and optionally skip the judge.
- **Evicts stale entries** based on time‑to‑live (TTL) and capacity limits to keep the cache performant.

## How It Works

### 1. Hashing

When a request arrives, the cache builds a **semantic hash** using SimHash (similarity hashing) over the prompt and the conversation context (the list of previous messages). This hash is a 64‑bit integer expressed as a hexadecimal string.

```python
from sentinelrouter.sentinelrouter.semantic_cache import SemanticCache

semantic_hash = cache.build_semantic_hash(prompt, messages)
```

The hash is deterministic: identical prompts with identical context produce the same hash. Similar prompts (with small variations) produce hashes that are close in Hamming distance, allowing the cache to detect near‑duplicates (though the current implementation uses exact hash matching for simplicity).

### 2. Recording an Interaction

After a request is completed, the router calls `record_interaction()` with:

- Prompt and context
- Response text (truncated to 500 characters for storage)
- Model used, latency, cost, token counts
- Whether the judge was invoked, its latency, complexity score, and impact scope

The cache creates two kinds of records:

- **`SemanticCacheEntry`**: A detailed row per interaction, storing the exact metadata.
- **`SemanticCacheStats`**: Aggregated statistics for the hash, updated incrementally.

### 3. Confidence Calculation

Confidence is defined as the proportion of the dominant model choice among all recorded calls for a given hash.

```
confidence = max(weak_calls, strong_calls, other_calls) / total_calls
```

- **Minimum samples**: The cache requires at least `semantic_cache_min_samples` (default 3) calls before it returns a non‑zero confidence.
- **Confidence threshold**: A hash is considered “confident” if its confidence exceeds `semantic_cache_confidence_threshold` (default 0.75, i.e., 75 %).

### 4. Cache‑Based Routing

When the router receives a new request, it first looks up the semantic hash in the cache:

```python
confident, confidence = cache.has_confident_history(prompt, messages)
if confident:
    recommendation = cache.get_recommended_route(prompt, messages)
    # recommendation is "weak", "strong", or None
```

If the cache is confident and returns a recommendation, the router may **skip the judge entirely** and route directly to the recommended model tier. This saves judge latency (typically 1–2 seconds) and reduces API costs.

The router logs cache hits and the resulting skip decisions for observability.

## Integration with Routing Logic

The semantic cache is consulted at the very beginning of the routing pipeline (`router_logic.py`, lines 109–139). The decision flow is:

1. Compute semantic hash.
2. Look up cached stats.
3. If cache has confident history:
   - Determine whether weak or strong models were predominantly used.
   - Skip judge (`cache_skip_judge = True`).
   - Set complexity score and impact scope to reflect the cache decision (0.0/LOW for weak, 0.95/HIGH for strong).
4. If cache does not have confident history, proceed with normal judge logic.

Cache recommendations are **advisory**, not mandatory. The router still respects cycle detection, budget limits, and throttling. However, when the cache is confident, the judge is skipped, which reduces latency and cost.

## Configuration

The semantic cache is configured via environment variables (with defaults defined in `config.py`):

| Variable | Default | Description |
|----------|---------|-------------|
| `SEMANTIC_CACHE_MIN_SAMPLES` | 3 | Minimum number of calls for a hash to be considered confident. |
| `SEMANTIC_CACHE_CONFIDENCE_THRESHOLD` | 0.75 | Confidence threshold (0.0–1.0). A hash must have a dominant model choice exceeding this fraction to be considered confident. |
| `SEMANTIC_CACHE_TTL_SECONDS` | 7 days | Time‑to‑live for cache entries. Entries older than this are automatically evicted. |
| `SEMANTIC_CACHE_MAX_ENTRIES` | 10 000 | Maximum number of detailed entries (`SemanticCacheEntry`) before oldest entries are deleted. |

These settings can be adjusted in the `.env` file or via Docker environment variables.

## Database Schema

The cache uses two SQLite tables (defined in `sentinelrouter/models.py`):

### `semantic_cache_entries`

| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PRIMARY KEY | Auto‑incrementing row ID. |
| `semantic_hash` | VARCHAR(64) | The computed hash (hex string). |
| `context_hash` | VARCHAR(64) | Hash of the context (messages) alone. |
| `prompt_preview` | TEXT | First 500 characters of the prompt. |
| `response_preview` | TEXT | First 500 characters of the response. |
| `latency_ms` | FLOAT | Total request latency (including judge if called). |
| `judge_invoked` | BOOLEAN | Whether the judge was called. |
| `judge_latency_ms` | FLOAT | Time spent in the judge (if invoked). |
| `model_used` | VARCHAR(64) | Model identifier (e.g., `deepseek‑chat`). |
| `complexity_score` | FLOAT | Judge’s complexity score (if judge invoked). |
| `impact_scope` | VARCHAR(16) | Judge’s impact scope (`LOW`/`MEDIUM`/`HIGH`). |
| `cost` | FLOAT | Cost incurred for this call. |
| `total_tokens` | INTEGER | Total tokens used (input + output). |
| `created_at` | DATETIME | Timestamp of the entry. |

### `semantic_cache_stats`

| Column | Type | Purpose |
|--------|------|---------|
| `semantic_hash` | VARCHAR(64) PRIMARY KEY | The hash (hex string). |
| `first_seen_at` | DATETIME | When this hash first appeared. |
| `last_called_at` | DATETIME | When this hash was last used. |
| `total_calls` | INTEGER | Total number of calls for this hash. |
| `weak_calls` | INTEGER | Number of calls that used a weak‑tier model. |
| `strong_calls` | INTEGER | Number of calls that used a strong‑tier model. |
| `judge_invocations` | INTEGER | Number of times the judge was invoked for this hash. |
| `total_latency_ms` | FLOAT | Sum of all latencies. |
| `total_latency_ms_sq` | FLOAT | Sum of squares of latencies (for variance calculation). |
| `total_cost` | FLOAT | Total cost incurred across all calls. |
| `total_tokens` | INTEGER | Total tokens across all calls. |
| `last_model` | VARCHAR(64) | Most recently used model. |

The stats table is updated incrementally each time a new entry is added, providing fast aggregations without scanning the detailed entries.

## Maintenance and Eviction

The cache automatically manages its size and freshness:

- **TTL eviction**: Entries older than `SEMANTIC_CACHE_TTL_SECONDS` are deleted from both tables during `record_interaction()`.
- **Capacity eviction**: If the total number of detailed entries exceeds `SEMANTIC_CACHE_MAX_ENTRIES`, the oldest entries are removed (FIFO).

These mechanisms prevent unbounded growth and keep the cache responsive.

## Metrics and Monitoring

The semantic cache emits metrics via the `MetricsCollector`:

- `semantic_cache_lookups_total`: Counter of cache lookups, labeled by hit/miss.
- `semantic_cache_confident_hits_total`: Counter of confident cache hits that influenced routing.
- `semantic_cache_entries_total`: Gauge of current entry count.
- `semantic_cache_evictions_total`: Counter of entries evicted (TTL or capacity).

These metrics are exposed on the dashboard’s Prometheus endpoint (`/dashboard/api/v1/metrics`) and can be used to tune cache parameters.

## Tuning Guidelines

### When to Increase Confidence Threshold

If the cache is causing inappropriate routing (e.g., skipping the judge for prompts that actually need strong models), raise the confidence threshold to 0.85 or 0.90. This requires a more dominant preference before the cache overrides the judge.

### When to Increase Minimum Samples

If the system sees high variability in early interactions (e.g., the first two calls used weak models, the third used strong), increase `SEMANTIC_CACHE_MIN_SAMPLES` to 5 or 10. This delays cache influence until more data is available.

### When to Adjust TTL

For applications with rapidly changing user behavior, a shorter TTL (e.g., 24 hours) may be appropriate. For stable workloads, a longer TTL (weeks) allows the cache to accumulate more history.

### When to Increase Capacity

If the cache is evicting entries too quickly because of capacity limits, increase `SEMANTIC_CACHE_MAX_ENTRIES`. Each entry uses about 1 KB of storage, so 10 000 entries ≈ 10 MB.

## Limitations

1. **Exact hash matching**: The current implementation only matches exact semantic hashes. Two prompts that are semantically similar but not identical will not be recognized as the same. Future versions may introduce similarity‑based lookup using Hamming distance.

2. **No cost‑awareness**: The cache does not consider the cost difference between weak and strong models when making recommendations. It simply follows the majority vote.

3. **Static configuration**: Cache parameters are set at startup and cannot be changed without restarting the server. Dynamic reconfiguration could be added in the future.

## Example

Consider a prompt that asks for the weather in San Francisco. The first three times it is seen, the judge is called and each time the complexity score is low, so the request is routed to the weak model (DeepSeek). The cache records:

- `weak_calls = 3`, `strong_calls = 0`, `total_calls = 3`
- Confidence = 1.0 (exceeds threshold 0.75)

The fourth time the same prompt appears, the cache lookup returns `confident = True` and recommends “weak”. The router skips the judge, saves ~1.5 seconds, and routes directly to DeepSeek.

If later the same prompt is asked during a severe‑weather scenario and the judge (if called) would return a high complexity score, the cache would still recommend weak because its history is based on past decisions. This is a trade‑off: the cache assumes past patterns will continue. The dynamic threshold and cycle detection modules provide safety nets for such edge cases.

---

*Last updated: 2025‑12‑14*  
*See also: [Routing Logic](routing-logic.md), [Configuration Guide](../getting-started/configuration.md)*