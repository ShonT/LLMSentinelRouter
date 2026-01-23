Below is a **ready-to-drop Issue Document** you can paste into GitHub (or Notion/Jira) for the **Admin UI changes**.
It is written in **operator / infra style**, with clear scope, rationale, acceptance criteria, and non-goals.

---

# Admin UI: Operator-Grade Policy Editing & Read-Only Visibility

## Context

SentinelRouter has evolved from a rule-based router into a **policy-driven, learning system** (semantic cache, judge, escalation rate control).
However, the current Admin UI surface is **under-specified** and mixes low-level defaults with high-impact behavior, making it hard for operators to know:

* what is safe to edit at runtime
* what requires restart
* what is learned vs configured
* what the system is currently doing and why

This issue formalizes a **clear separation between static config, editable policy, and read-only state**, enabling confident operation without accidental topology changes.

---

## Goals

1. Define a **safe, explicit set of admin-editable fields** (policy knobs only).
2. Ensure **all structural config remains file-based / restart-required**.
3. Add **read-only visibility** for models, routing, judge, and semantic cache state.
4. Make **session / state impact explicit** when admin values change.
5. Increase operator confidence and explainability without expanding blast radius.

---

## Non-Goals

* No editing of API keys, key instances, or model definitions via Admin UI
* No live editing of routing topology (weak/strong tiers, order)
* No UI redesign required (API-level changes are sufficient)
* No change to core routing logic in this issue

---

## Current State (Before)

### Editable via Admin API

`POST /api/dashboard/session-defaults`

* `default_tier`
* `default_use_judge`
* `session_id_strategy`
* `default_session_id`

### Issues

* These fields are **low-level and implicit**
* No budget or semantic controls exposed
* No indication of blast radius
* No visibility into:

  * weak vs strong routing
  * judge behavior
  * semantic cache effectiveness
  * escalation rate

---

## Proposed State (After)

### A. Admin-Editable Fields (Policy Only)

These fields are **safe to edit at runtime** and should be backed by an `AdminPolicyConfig`.

#### Budget & Escalation Policy

* `budget_control.max_cost_per_session`
* `budget_control.escalation_rate_limit`
* `budget_control.rolling_window_size`

#### Judge Policy

* `judge.enabled`
* `judge.mode`
* `judge.complexity_threshold`

#### Semantic Cache Policy

* `semantic_cache.enabled`
* `semantic_cache.min_samples`
* `semantic_cache.confidence_threshold`
* `semantic_cache.ttl_seconds`

#### Cycle Detection

* `cycle_detection.enabled`
* `cycle_detection.window_size`
* `cycle_detection.simhash_distance_threshold`

✅ These affect **future routing decisions only**
✅ No topology or credential risk
✅ No restart required

---

### B. Session / State Impact Rules

Admin UI must clearly indicate impact per field change.

#### Immediate Effect (No Refresh Required)

* `judge.enabled`
* `judge.mode`
* `complexity_threshold`
* `escalation_rate_limit`
* `semantic_cache.confidence_threshold`
* `cycle_detection.enabled`

#### Soft State Reset Recommended

* `semantic_cache.min_samples`
* `semantic_cache.ttl_seconds`
* `rolling_window_size`

Expected action:

* reset semantic cache
* reset escalation counters
  (no session restart)

#### Warning Required

* `max_cost_per_session`

UI copy example:

> “This change may immediately block in-flight sessions that exceed the new budget.”

---

### C. Read-Only Admin UI (Critical)

The following must be **visible but not editable**.

#### 1. Static Configuration (Read-Only)

* Models list
* Provider + model_id
* Enabled / disabled status
* Weak vs strong tier membership
* Routing order
* Key instance association (masked)

#### 2. Routing & Judge State (Read-Only)

* Current escalation rate
* Current effective thresholds
* Strong vs weak routing ratio
* Judge invoked vs skipped rate

#### 3. Semantic Cache State (Read-Only)

* Cache hit rate
* Confidence distribution
* Number of active semantic clusters
* Judge-skip attribution (cache vs policy)

Purpose:

> Allow operators to understand *why* the router behaves as it does.

---

## Acceptance Criteria

### Functional

* [ ] Admin UI exposes **only** approved policy fields for editing
* [ ] Static config (keys, models, routing tiers) is not editable
* [ ] Editing a policy field applies without restart
* [ ] Required cache/counter resets are triggered or clearly indicated

### Safety

* [ ] No admin action can modify routing topology
* [ ] No admin action can expose or modify secrets
* [ ] UI warns when changes affect existing sessions

### Observability

* [ ] Operators can view weak/strong routing configuration
* [ ] Operators can see judge and semantic cache effectiveness
* [ ] Operators can inspect escalation behavior over time

---

## Rationale (Why this matters)

Without this separation:

* Operators are afraid to tune the system
* Debugging relies on logs and guesswork
* Small config changes can have unclear blast radius

With this change:

* Admin UI becomes a **policy console**, not a footgun
* Learning systems become observable and trustworthy
* The system is explainable under load and incidents

---

## One-Sentence Principle

> **Admins may tune policy and learning, but may not alter execution topology or credentials.**

---

If you want, next I can:

* derive an `AdminPolicyConfig` Pydantic model from this
* map existing endpoints → new admin endpoints
* or help you write the **exact UI copy/tooltips** operators will see
