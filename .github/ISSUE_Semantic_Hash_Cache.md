# Proposal: Semantic-Hash Request/Response Cache

## Summary
Create a semantic-hash based cache for request/response behavior to reduce redundant calls to the judge and LLMs. For every request/response pair store:

- Semantic hash (SimHash or other) of the request + context
- Time taken for the request
- Whether the judge was invoked (Yes/No)
- Which model was called
- Result metadata (complexity, impact, cost, tokens)
- Timestamps and frequency of calls

Use the cache to:
- Quickly decide to skip judge calls for known requests that historically route to the weak model.
- Skip weak calls and directly call the strong model when cache indicates strong is required (optionally verify with judge before call).
- Track runtimes and costs per semantic-hash to build confidence on routing decisions.

## Design Notes
- Use the existing `CycleDetector`'s simhash helper or extract a dedicated `SimHash` utility for hashing.
- Store entries in a lightweight local DB (SQLite) and expose eviction/TTL policies.
- Maintain call statistics per hash (counts, mean latency, variance, last called timestamp).
- Add a confidence threshold: only skip judge when call history for a hash crosses a configurable confidence level.

## Acceptance Criteria
- Cache key generation consistent (semantic + context aware)
- Cache lookups are fast and used before judge invocation
- Cache records judge usage and model used per request
- Dashboard/metrics show cache hit/miss rates and benefits

## Status
Planned (issue filed for later implementation)
