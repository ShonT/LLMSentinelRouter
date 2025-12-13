# Proposal: Model-State Server (external config & telemetry provider)

## Summary
Create a small service (Model-State Server) that exposes the router's current view of model health, costs, throttles, and recommended routing configuration. The router can query this service to get the latest best-configuration for fast/long-running answers.

## Responsibilities
- Aggregate telemetry from running routers (latency, errors, rate limits, cost)
- Compute recommended routing order and priorities based on live performance
- Provide an API endpoint for routers to fetch current strategy/configuration
- Optionally provide a UI for operators to override automated recommendations

## Benefits
- Centralized coordination for multi-router deployments
- Ability to perform dynamic reconfiguration without restarting routers
- Smarter routing decisions based on global state

## Acceptance Criteria
- REST API that returns model status and recommended routing order
- Compatible client library or simple HTTP client integration in router
- Secure access (basic auth or token) and rate-limited

## Status
Planned (issue filed for later implementation)
