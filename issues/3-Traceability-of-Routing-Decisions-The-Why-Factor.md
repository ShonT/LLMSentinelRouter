# Traceability of Routing Decisions (The "Why" Factor)

## The Issue
While tracking latency is good, the dashboard often misses the Contextual Metadata—why a specific request was routed to "Provider A" instead of "Provider B."

## Why It's Critical
If you are testing high‑scale system designs, you need to see the "functional reasoning" of the router per request. Was it routed because of a cached health check? A weighted round‑robin? Or a fallback because of a 429 error?

## Proposed Fix
Include a "Routing Trace" column in your request log. This should display the specific rule or health‑check result that triggered that specific path, paired with the latency breakdown mentioned in point #1.

## Implementation Details
1. Extend the router’s decision‑making logic to emit a structured "trace" object for each request. The trace should capture:
   - The list of candidate providers evaluated.
   - The health‑check result (latency, error rate, etc.) for each candidate.
   - The final selection reason (e.g., `"lowest_latency"`, `"fallback_after_429"`, `"weighted_random"`, `"semantic_cache_hit"`).
   - Any overrides from admin policies or session‑level rules.
2. Store this trace as a JSON field (e.g., `routing_trace`) in the request log.
3. Update the dashboard’s request‑log table to include a new column "Routing Trace" that shows a concise, human‑readable summary (e.g., "Fallback to Groq after OpenAI 429").
4. Make the column expandable—clicking reveals the full trace with timestamps, scores, and rule details.
5. Ensure the trace is also available via the API (`GET /requests/{id}`) for automated analysis.

## Related Components
- `sentinelrouter/router_logic.py` (decision logging)
- `sentinelrouter/metrics.py` (trace storage)
- `sentinelrouter/dashboard.py` (UI column)
- `sentinelrouter/schemas/config_models.py` (trace schema)

## Example Trace
```json
{
  "request_id": "req_abc123",
  "candidates": [
    {"provider": "openai", "model": "gpt‑4", "health_score": 0.95, "latency_ms": 320},
    {"provider": "groq", "model": "llama‑3‑70b", "health_score": 0.98, "latency_ms": 180}
  ],
  "selected_provider": "groq",
  "selected_model": "llama‑3‑70b",
  "reason": "lowest_latency",
  "rule_applied": "weighted_health_check",
  "timestamp": "2026‑01‑26T22:43:00Z"
}
```

## Priority
High – essential for understanding router behavior and debugging complex routing scenarios.