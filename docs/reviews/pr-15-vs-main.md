## Migration review vs `main` (Cloud Agent)

Compared `ketan/go-migration` to `main`. This is a full runtime replacement (~46k lines removed, ~5k added), not an incremental port.

### Verdict: Was the migration perfect?

**No.** Route coverage is strong and core routing works, but several subsystems are simplified, stubbed, or only partially ported. Treat this as a **functional rewrite with API parity on paper**, not a behavior-preserving drop-in.

---

### 1. Endpoints, schemas, and interfaces

**Endpoints — largely preserved.** All HTTP routes from Python (`server.py` + `dashboard.py`) appear on the Go mux (gateway, dashboard, admin). Removed from the surface: FastAPI `/docs`, `/redoc`, and the Python package layout.

**Request/response shapes — mostly aligned, with gaps:**

| Topic | `main` (Python) | Go PR |
|-------|-----------------|-------|
| Budget error HTTP code | **402** (middleware + router) | **429** |
| `stream: true` | Accepted in schema | Passed to provider but **no SSE/chunked response** — still returns one JSON body |
| Message `content` | Coerced to string if non-string | Must be non-empty string |
| Last user message | Uses **last** user message | Uses **first** user message in loop |
| OpenAI `model` field | Present in Pydantic model | Parsed but **not used** for routing |

**Config schema** — `SentinelConfig` is ported with Go validation comparable to Pydantic. Legacy `models_config.json` fallback is kept.

---

### 2. Same functionality?

**Partially.** Core path works (routing, budget gate, judge modes, failover, rate limits, redaction, metrics JSONL, SQLite audit for routing decisions). Important gaps:

- `GET /api/dashboard/metrics` returns **hard-coded zeros** for fallbacks, judge latency series, judge success/skip rates, etc. (`server.go` ~413–427). Python aggregated real metrics from the collector.
- `GET /api/admin/state` returns **stub judge/semantic_cache counters** (all zeros) (~854–855).
- Python wired observability to DB + collectors; Go dashboard/admin views will look empty vs `main`.

---

### 3. Same dependencies (DB, etc.)?

| Dependency | `main` | Go PR |
|------------|--------|-------|
| SQLite | SQLAlchemy | `modernc.org/sqlite` — same `DATABASE_URL` style |
| Provider HTTP | `httpx` async | `net/http` sync |
| Config hot-reload | `config_manager` | `config.Manager` + file watch |
| Optional ML stack | onnx/transformers/lancedb/networkx | **Removed** |
| CI live API secrets | Integration job used provider secrets | **Removed** — mock-based tests only |

Docker ports `8000`/`8001` preserved; Go can serve the same handler on both (cleaner than Python’s separate dashboard thread).

---

### 4. Removed functionality

| Feature | Notes |
|---------|--------|
| Semantic cache persistence | Python: SQLite-backed; Go: **in-memory only** (DB tables created but never written) |
| `escalation_traces` | Python table + audit; **not created in Go** |
| `cycle_detection` / `escalation_log` DB writes | Tables exist in Go schema; **no inserts** |
| Enhanced cycle detection | VECTORDB_LOCAL/API + LanceDB → SimHash-only in-memory |
| Judge registry + circuit breaker | → Simple `judge.ModelOrder` loop + heuristic fallback |
| StateManager + WAL | → Session defaults + much state **in-memory** |
| Budget OCC | Versioned reserve/commit → simple `UPDATE current_cost` (**race risk**) |
| Budget middleware (early 402 on `X-Session-ID`) | Only in router; different status code |
| ~30 Python test modules | → **5** `_test.go` files; router/budget/storage largely untested |
| `POST /api/dashboard/reset-all-costs` | Python reset all model costs; Go returns success **without resetting** (~399–401) |

`setAllModelsEnabled` exists in Go but appears **unused** (dead code).

---

### 5. Improvements

- Single static binary; smaller deploy surface; no Python/ML deps
- Unified API + dashboard handler (optional dual port)
- **Start/stop all** actually updates runtime status (Python handlers were comment stubs)
- Admin key update: atomic JSON + `ForceReload()`
- Reliable CI via httptest fake providers
- Explicit test for conditional judge timeout escalation
- `sentinelrouter healthcheck` for Docker

---

### 6. Issues to address before “production parity”

**Critical / high**

1. `POST /api/dashboard/reset-all-costs` is a no-op
2. Semantic cache not durable across restarts
3. `stream: true` does not stream to clients
4. Budget races without OCC under concurrent requests
5. HTTP **402 → 429** for budget — client-breaking
6. Admin policy / session defaults lost on restart
7. Test coverage collapse (router, budget, judge, provider untested)

**Medium**

8. Dashboard metrics & admin state stubs break charts
9. First vs last user message for prompt extraction
10. Dead DB tables (`semantic_cache_*`, `cycle_detection`, `escalation_log`) with no writers
11. Go 1.26.x — confirm org toolchain support

**Low**

12. No OpenAPI `/docs` (document elsewhere if intentional)
13. Dashboard still exposes raw API keys (same as Python — consider masking)

---

### Suggestions

1. Automated contract/parity tests per route + golden JSON
2. Wire semantic cache to SQLite or drop unused tables
3. Implement `dashboardResetAllCosts` + real metrics aggregation
4. Implement SSE streaming or reject `stream: true` with 400
5. Restore budget OCC or document single-writer assumption
6. Persist session defaults for operators
7. Port high-value unit tests from `main`
8. Publish a migration guide (402→429, cache, streaming, judge behavior)

---

### Summary

| Criterion | Assessment |
|-----------|------------|
| Endpoint/schema parity | Routes **yes**; behavior **partial** |
| Same functionality | **~70%** |
| Same dependencies | SQLite yes; ML/vector deps no |
| Removed functionality | **Yes** (material) |
| Improved | **Yes** (ops/CI) |
| Perfect migration? | **No** |

**Recommendation:** Strong foundation for a Go runtime, but needs a **behavior parity pass** before calling this a complete replacement of `main`. Happy to re-review after reset-all-costs, semantic cache persistence, dashboard metrics/admin state, streaming, and budget concurrency are addressed.
