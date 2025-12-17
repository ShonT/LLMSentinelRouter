# SentinelRouter Enhancement Plan

## 1. Executive Summary

The SentinelRouter system is a production‑ready local API gateway that intelligently routes LLM requests between weak (DeepSeek) and strong (Anthropic Claude) models based on complexity, budget, and session‑based limits. The current implementation provides a solid foundation with four core modules (Budget Kill‑Switch, Stingy Judge, Dynamic Thresholding, Cycle Detection) and a basic dashboard.

This enhancement plan introduces three major improvements:

1. **Unified Configuration Schema** – Replace scattered environment variables and SQLite‑stored settings with a single `models_config.json` file that defines system‑wide settings, model capabilities, routing priorities, rate limits, pricing tiers, and real‑time state.

2. **Write‑Behind Async Persistence** – Shift from SQLite‑first persistence to an in‑memory‑first architecture where all reads are served from RAM (microsecond latency) and writes are asynchronously flushed to disk using an atomic write‑behind pattern. This eliminates database bottlenecks and improves throughput while maintaining crash resilience.

3. **Enhanced Three‑Tab Dashboard** – Extend the existing dashboard with three dedicated tabs:
   - **Live Traffic** – Operational view with RPM gauges, session cost, and emergency controls.
   - **Configuration & Keys** – Administrative interface for API‑key management, pricing‑tier editing, and priority drag‑and‑drop.
   - **Router Logic** – Diagnostic view showing routing decision logs and explanations.

These changes will make the system more maintainable, performant, and operator‑friendly, while preserving backward compatibility for existing clients.

## 2. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            Client Requests                              │
│                        (OpenAI‑compatible API)                          │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         FastAPI Server (Port 8000)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────────┐  │
│  │ Budget       │  │ Cycle        │  │ Request/Response            │  │
│  │ Kill‑Switch  │  │ Detection    │  │ Logging                     │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          Router Logic                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────────┐  │
│  │ Stingy       │  │ Dynamic      │  │ Model/Judge                  │  │
│  │ Judge        │  │ Threshold    │  │ Registries                   │  │
│  │ (w/ backup)  │  │ (5% Rule)    │  │ (w/ circuit breakers)        │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     State Manager (Write‑Behind)                        │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                        In‑Memory State                          │   │
│  │  • Model configs, limits, pricing                               │   │
│  │  • Real‑time counters (RPM, tokens, costs)                      │   │
│  │  • Dirty flags for changed entries                              │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                 │                                      │
│                        ┌────────┴────────┐                            │
│                        │  Background     │                            │
│                        │  Worker (every  │                            │
│                        │  N seconds)     │                            │
│                        └────────┬────────┘                            │
│                                 │                                      │
│                        ┌────────▼────────┐                            │
│                        │  Atomic Write   │                            │
│                        │  • .tmp → .json │                            │
│                        │  • OS rename    │                            │
│                        └─────────────────┘                            │
└─────────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Enhanced Dashboard (Port 8001)                       │
│  ┌─────────────────┐ ┌─────────────────┐ ┌──────────────────────────┐  │
│  │ Live Traffic    │ │ Configuration   │ │ Router Logic             │  │
│  │ • RPM gauges    │ │ • API‑key mgmt  │ │ • Decision logs          │  │
│  │ • Cost progress │ │ • Pricing tiers │ │ • Last decision explain  │  │
│  │ • Emergency stop│ │ • Drag‑and‑drop │ │                          │  │
│  └─────────────────┘ └─────────────────┘ └──────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     External LLM Providers                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────────┐  │
│  │ DeepSeek     │  │ Anthropic    │  │ Gemini (backup)              │  │
│  │ (weak tier)  │  │ (strong tier)│  │                              │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

**Data Flow:**
1. Client request enters via FastAPI.
2. Budget middleware checks session cost.
3. Router logic uses judge, threshold, and cycle detection to pick a model.
4. Model registry selects an available provider (with failover).
5. Response is returned, and cost is added to session.
6. State manager updates in‑memory counters and marks data dirty.
7. Background worker periodically writes dirty state to `models_config.json`.
8. Dashboard reads from in‑memory state for real‑time display.

## 3. Implementation Phases

The work will be split into four sequential phases to minimize disruption and allow incremental testing.

**Phase 1 – Configuration & Data Models**
- Define new Pydantic models for the unified configuration schema.
- Create `models_config.json` with backward‑compatible defaults.
- Update `config.py` to load the new JSON and merge with environment variables.
- Write migration script to convert existing SQLite settings to JSON.

**Phase 2 – State Manager & Write‑Behind Persistence**
- Implement `StateManager` class with in‑memory dictionaries and dirty‑flag tracking.
- Add background worker thread that flushes dirty entries every N seconds.
- Implement atomic write via temporary file + rename.
- Replace direct SQLite reads in router logic with state‑manager queries.
- Keep SQLite for audit logs (routing decisions, cycles) unchanged.

**Phase 3 – Dashboard Enhancements**
- Extend `dashboard.py` with three‑tab layout.
- Build Live Traffic tab with real‑time gauges (using SSE or periodic AJAX).
- Build Configuration tab with masked API‑key display and editable forms.
- Build Router Logic tab with decision log table and “last decision” explanation.
- Connect dashboard to state manager for live data.

**Phase 4 – Integration & Testing**
- Update `router_logic.py` to use new configuration and state manager.
- Run comprehensive integration tests with mocked providers.
- Perform load testing to verify write‑behind performance.
- Create rollback plan and deploy.

## 4. File Changes Required

### New Files
- `sentinelrouter/sentinelrouter/state_manager.py` – Write‑behind persistence engine.
- `sentinelrouter/schemas/config_models.py` – Pydantic models for the new configuration.
- `sentinelrouter/schemas/dashboard_models.py` – Pydantic models for dashboard API.
- `config/models_config.json` – Default configuration file (versioned).
- `scripts/migrate_sqlite_to_json.py` – One‑time migration script.

### Modified Files
- `sentinelrouter/sentinelrouter/config.py` – Load JSON config, provide settings object.
- `sentinelrouter/sentinelrouter/router_logic.py` – Use state manager instead of direct SQLite for model limits.
- `sentinelrouter/sentinelrouter/dashboard.py` – Three‑tab UI, new endpoints.
- `sentinelrouter/sentinelrouter/metrics.py` – Add metrics for state‑manager operations.
- `sentinelrouter/sentinelrouter/server.py` – Inject state manager into request context.
- `sentinelrouter/sentinelrouter/model_registry.py` – Read model limits from state manager.
- `sentinelrouter/sentinelrouter/judge_registry.py` – Read judge configuration from state manager.
- `docker‑compose.yml` – Mount config directory as volume.
- `requirements.txt` – Add optional dependencies for dashboard (e.g., fastapi‑websockets).

### Unchanged Files
- `sentinelrouter/sentinelrouter/budget.py` – Still uses SQLite for session cost (budget is per‑session, not model‑specific).
- `sentinelrouter/sentinelrouter/cycle_detector.py` – No changes.
- `sentinelrouter/sentinelrouter/logging_audit.py` – No changes.
- `sentinelrouter/sentinelrouter/clients.py` – No changes.

## 5. New Data Models

### Pydantic Models (in `schemas/config_models.py`)

```python
from pydantic import BaseModel, Field
from typing import Dict, List, Literal, Optional
from datetime import datetime

class SystemSettings(BaseModel):
    persistence_interval_seconds: int = 5
    default_routing_strategy: Literal["waterfall", "priority"] = "waterfall"
    timezone: str = "UTC"

class ModelCapabilities(BaseModel):
    modality: List[Literal["text", "image", "audio"]] = ["text"]
    context_window: int = 128000

class RoutingConfig(BaseModel):
    priority_group: Literal["fast_tier", "strong_tier"] = "fast_tier"
    order: int = 1

class RateLimits(BaseModel):
    requests_per_minute: int = 15
    requests_per_day: int = 1500
    tokens_per_minute: int = 1_000_000

class PricingTier(BaseModel):
    name: str
    threshold_requests: int | Literal["inf"]
    input_cost: float
    output_cost: float

class PricingInfo(BaseModel):
    currency: str = "USD"
    input_cost_per_m: float = 0.0
    output_cost_per_m: float = 0.0
    usage_tiers: List[PricingTier] = []

class ModelState(BaseModel):
    current_rpm: int = 0
    requests_today: int = 0
    tokens_today: int = 0
    total_cost_session: float = 0.0
    last_updated_ts: Optional[datetime] = None
    exhausted_until_ts: Optional[datetime] = None

class ModelConfig(BaseModel):
    display_name: str
    provider: str
    status: Literal["active", "inactive", "disabled"] = "active"
    capabilities: ModelCapabilities
    routing: RoutingConfig
    limits: RateLimits
    pricing: PricingInfo
    state: ModelState = Field(default_factory=ModelState)

class UnifiedConfig(BaseModel):
    system_settings: SystemSettings
    models: Dict[str, ModelConfig]  # key = model_id
```

## 6. State Manager Design

### Class: `StateManager`

**Responsibilities:**
- Hold in‑memory copy of `UnifiedConfig`.
- Provide thread‑safe read/write access via `asyncio.Lock`.
- Track dirty models (whose `state` has changed) with a `Set[str]`.
- Expose methods: `get_model_config(model_id)`, `update_model_state(model_id, **updates)`.
- Start a background asyncio task that runs every `persistence_interval_seconds`.

**Write‑Behind Algorithm:**
1. On startup, load `models_config.json` into memory.
2. Any state update (e.g., increment `requests_today`) marks the model as dirty.
3. Background task wakes up, acquires lock, copies dirty entries to a temporary dictionary.
4. Writes the entire config to a temporary file (`models_config.json.tmp`).
5. Atomically renames the temporary file to `models_config.json` (POSIX guarantee).
6. Clears the dirty set.

**Crash Resilience:**
- If the process crashes between steps 4‑5, the temporary file is ignored on next load (the previous `.json` is intact).
- At most `persistence_interval_seconds` of state changes can be lost (acceptable trade‑off).

**Concurrency:**
- Use `asyncio.Lock` for mutations; reads can be lock‑free (dict reference is stable).
- The background task holds the lock only while copying dirty entries, not during file I/O.

## 7. Dashboard Enhancements

### Tab 1: Live Traffic
- **UI**: Table with columns: Model Name, Status Badge, RPM Gauge, Requests Today (progress bar), Session Cost.
- **Controls**: “Reset Session Cost” button (calls `POST /dashboard/api/v1/reset_cost`), “Emergency Stop” toggle per model (disables routing to that model).
- **Data Source**: SSE stream from `/dashboard/events` that pushes state updates every second.

### Tab 2: Configuration & Keys
- **UI**: Form‑based editor for `models_config.json` with validation.
- **Features**:
  - API‑key masking (`sk‑...45a`).
  - Add/remove pricing tiers.
  - Drag‑and‑drop priority ordering within a tier.
  - Rate‑limit sliders.
- **Save Mechanism**: Explicit “Save” button writes to state manager (which triggers write‑behind).

### Tab 3: Router Logic
- **UI**: Table of last 50 routing decisions with columns: Timestamp, Session, Prompt Snippet, Complexity Score, Impact Scope, Model Chosen, Cost.
- **Diagnostic Panel**: “Last Routing Decision” – shows the exact reasoning: e.g., “User asked X → Router picked Model A because Model B was throttled.”

### Backend Changes
- New FastAPI router under `/dashboard/api/v1/` with endpoints:
  - `GET /state` – returns current in‑memory state.
  - `POST /state` – updates configuration (admin only).
  - `GET /decisions` – paginated routing decisions.
  - `GET /events` – Server‑Sent Events stream for live updates.

## 8. Migration Strategy

1. **Backup Existing Data**: Script creates a backup of `sentinelrouter.db` and the current `.env` file.
2. **Run Migration Script**: `python scripts/migrate_sqlite_to_json.py` reads the SQLite `model_config` table (if any) and the environment variables, then generates a `models_config.json` in the new format.
3. **Rolling Deployment**:
   - Deploy new code that can read both old (SQLite) and new (JSON) configurations.
   - Use a feature flag to switch between persistence modes.
   - After verification, disable SQLite writes for model‑specific state (keep SQLite for session budget and audit logs).
4. **Rollback Plan**: If critical issues arise, revert to previous version that uses SQLite exclusively; the JSON file will be ignored.

## 9. Testing Strategy

### Unit Tests
- `test_state_manager.py` – verify dirty‑flag tracking, atomic write, crash recovery.
- `test_config_models.py` – validate Pydantic schemas with edge cases.
- `test_dashboard_api.py` – endpoint authentication and data formatting.

### Integration Tests
- `test_write_behind.py` – simulate crashes and ensure config file integrity.
- `test_migration.py` – verify SQLite‑to‑JSON conversion correctness.
- `test_router_with_new_config.py` – ensure routing decisions respect new limits.

### Load & Performance Tests
- Use `locust` to simulate 100 concurrent sessions.
- Measure latency before/after write‑behind introduction (expected improvement).
- Verify background worker does not block request processing.

### Dashboard UI Tests
- Selenium tests for the three tabs (run in headless Chrome).
- Verify real‑time updates work via WebSocket/SSE.

## 10. Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Configuration file corruption | High | Low | Atomic writes with `.tmp` rename; keep last known good version. |
| Race conditions in dirty‑flag tracking | Medium | Medium | Use `asyncio.Lock`; thorough unit testing with concurrent scenarios. |
| Dashboard performance degrades with many models | Low | Medium | Paginate model list; use server‑side filtering. |
| Migration script fails on custom setups | High | Low | Provide manual migration instructions; validate before deploy. |
| Write‑behind worker stalls under heavy load | Medium | Low | Monitor task health; add watchdog timer to restart worker. |
| Backward compatibility broken for existing clients | High | Low | Keep API unchanged; test with existing client test suite. |

## Conclusion

This enhancement plan modernizes SentinelRouter’s configuration and persistence layers while delivering a more powerful operator dashboard. The phased approach allows incremental validation and reduces deployment risk. After implementation, the system will be easier to configure, more responsive, and provide better visibility into routing decisions.
