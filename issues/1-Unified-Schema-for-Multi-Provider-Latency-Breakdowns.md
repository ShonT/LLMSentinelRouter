# Unified Schema for Multi-Provider Latency Breakdowns

## The Issue
Currently, the dashboard likely tracks "total latency," but it lacks a standardized schema to visualize the internal breakdown of a request (DNS, Connection, TTFT, and Completion).

## Why It's Critical
In a local router, the "total time" is less important than the Breakdown of Components. You need to see if the delay is happening in your local routing logic, the network handshake, or the model's inference.

## Proposed Fix
Implement a stacked bar chart for every request showing:

- **Overhead**: Time spent in SentinelRouter logic.
- **TTFT (Time to First Token)**: Critical for UX.
- **Generation Time**: Time from first to last token.

## Implementation Details
1. Extend the existing metrics tracking to capture component‑level timestamps (DNS, Connection, TTFT, Completion, etc.).
2. Store these timestamps in a structured schema (e.g., a JSON field `latency_breakdown`) alongside each request log.
3. Update the dashboard’s request‑detail view to render a stacked bar chart that visually separates each component.
4. Ensure the chart is interactive—hovering reveals exact milliseconds and percentage of total latency.

## Related Components
- `sentinelrouter/metrics.py`
- `sentinelrouter/dashboard.py`
- `sentinelrouter/schemas/config_models.py` (for schema extension)

## Priority
High – directly impacts debugging and performance tuning of the router.