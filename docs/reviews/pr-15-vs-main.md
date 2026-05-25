# PR #15 parity resolution against current main

This branch was rechecked against `origin/main` at `ae3ef95` (`feat: Go migration parity, real SSE streaming, and judge circuit-breaker registry (#19)`) before resolving PR #15 conflicts.

## Conflict resolution

The conflicted Go runtime files were resolved by keeping the newer `main` implementation, because `main` already contains the PR #19 parity pass for the Go runtime. The merge brings in:

- Real SSE streaming for OpenAI-compatible providers, with buffered fallback for providers that do not expose native streaming yet.
- HTTP 402 for budget-exceeded errors.
- Last-user-message prompt extraction and non-string message content coercion.
- Persistent semantic cache, session defaults, runtime admin policy, audit records, budget state, and metrics-backed dashboard/admin state.
- Judge registry and circuit-breaker failover.
- Runtime reset-all-costs behavior.

## Remaining issue #17 follow-up

The remaining actionable item from issue #17 was dashboard exposure of raw API key values. `GET /api/dashboard/configuration` now returns masked key values, and the dashboard live-edit form treats masked values as placeholders so it does not submit them back as replacement keys.

## Contract coverage

The current Go test suite covers the parity items that were called out in the review:

- `TestChatBudgetExceededUses402`
- `TestChatStreamingIsSupported`
- `TestChatUsesLastUserMessageAndCoercesContent`
- `TestDashboardResetAllCostsClearsRuntimeTotals`
- `TestDashboardConfigurationMasksAPIKeys`
- `TestRuntimePolicyAndSessionDefaultsPersistAcrossServerRestart`
- `TestSemanticCachePersistsAcrossRouterRestart`
- `internal/judge` health tracker circuit-breaker tests

## Intentional semantics

- The OpenAI `model` request field is accepted for client compatibility, but routing remains policy-controlled by SentinelRouter tiers and judge/cache decisions.
- Anthropic and Gemini streaming currently use the normalized buffered fallback path; native provider-specific stream parsing can be added separately without changing the client-facing SSE contract.
