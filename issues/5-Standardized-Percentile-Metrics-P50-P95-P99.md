# Standardized Percentile Metrics (P50, P95, P99)

## The Issue
"Average Latency" is often a misleading metric for LLMs because it hides tail‑latency spikes that critically impact user experience. The dashboard currently lacks percentile‑based latency visualizations.

## Why It's Critical
In high‑scale systems, the "Big Tech" standard for measuring performance is tail latency (P95, P99). A single slow request can dominate the perceived slowness, while average latency may look acceptable. Providing P50 (median), P95 (95th percentile), and P99 (99th percentile) gives a true picture of latency distribution and helps identify outliers.

## Proposed Fix
Add toggleable cards to show P95 latency (and optionally P50, P99) alongside the current average‑latency display. The cards should be clickable to switch between percentile views.

## Implementation Details
1. **Metrics Collection** – Extend the existing latency‑tracking logic to store individual request latencies in a rolling window (e.g., last 10,000 requests) suitable for percentile calculation.
2. **Percentile Computation** – Implement a lightweight percentile calculator (e.g., using a sorted list or approximate algorithms like t‑digest) that can compute P50, P95, P99 on the fly for a given time range (last hour, last day, etc.).
3. **Dashboard UI** – Add three new metric cards (or a single card with a toggle) that display:
   - **P50 (Median)** – the latency below which 50% of requests fall.
   - **P95** – the latency below which 95% of requests fall (primary focus).
   - **P99** – the latency below which 99% of requests fall (worst‑case tail).
4. **Toggle Interaction** – Allow users to click a card to switch the main latency chart to show that percentile’s trend over time.
5. **Tooltips & Explanations** – Include a small info icon that explains what each percentile means and why it matters.

## Example UI
```
┌─────────────────────────────────────────────┐
│ Average Latency       P50       P95       P99 │
│   342 ms            310 ms    520 ms    890 ms │
└─────────────────────────────────────────────┘
```
Clicking "P95" would change the line chart to plot the 95th‑percentile latency per minute/hour.

## Related Components
- `sentinelrouter/metrics.py` (store raw latencies, compute percentiles)
- `sentinelrouter/dashboard.py` (UI cards and chart toggling)
- `sentinelrouter/schemas/config_models.py` (optional schema for percentile config)

## Performance Considerations
- Storing every request latency may increase memory usage. Consider sampling or using a bounded data structure (e.g., a circular buffer).
- Percentile calculations should be cached and updated periodically, not on every request.

## Priority
High – essential for production‑grade monitoring and performance debugging.