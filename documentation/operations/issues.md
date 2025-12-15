# SentinelRouter - Known Issues & Fixes Applied

**Code Review Date:** December 9, 2025  
**Status:** Issues Documented & Fixes Applied

---

## **CRITICAL ISSUES (P0 - Code Breaking)**

### 1. Missing Dependencies in requirements.txt
**Impact:** Container fails to start, imports fail  
**Location:** `requirements.txt`  
**Issue:**
- `pydantic-settings` not included (required by `config.py:9`)
- `gunicorn` not included (required by `Dockerfile:57`)
- `requests` library used in Docker health check but not in requirements

**Fix Applied:** Added missing dependencies to requirements.txt

---

### 2. Class Naming Mismatch - AuditLogger vs LoggingAudit
**Impact:** NameError/AttributeError on startup  
**Location:** `router_logic.py:40`, `logging_audit.py:86,233`  
**Issue:**
```python
# router_logic.py line 40
self.audit = AuditLogger(db_session)  # Wrong class name

# logging_audit.py has two classes:
# - AuditLogger (line 86) - just DB logger
# - LoggingAudit (line 233) - facade with both DB and file logging
```

**Fix Applied:** Changed router_logic.py to use `LoggingAudit` class

---

### 3. Missing session_cost in Router Response
**Impact:** KeyError when accessing response headers  
**Location:** `router_logic.py:201-209`, `server.py:297`  
**Issue:**
```python
# server.py:297 expects this header
"X-Sentinel-Session-Cost": str(result.get("session_cost", 0.0))

# But router_logic.py doesn't return session_cost in result dict (lines 201-209)
```

**Fix Applied:** Added `session_cost` to router response dictionary

---

### 4. Docker Health Check Uses Missing Library
**Impact:** Health check always fails, container marked unhealthy  
**Location:** `Dockerfile:53`  
**Issue:**
```dockerfile
CMD python -c "import requests; requests.get('http://localhost:8000/health', timeout=2)"
# requests library not in requirements.txt
```

**Fix Applied:** Changed to use `httpx` which is already in requirements

---

### 5. Gunicorn Command Not Found
**Impact:** Container fails to start  
**Location:** `Dockerfile:57`  
**Issue:**
```dockerfile
CMD ["gunicorn", "--bind", "0.0.0.0:8000", ...]
# gunicorn not in requirements.txt
```

**Fix Applied:** Added gunicorn to requirements.txt

---

### 6. Metrics Endpoint Wrong Query
**Impact:** Returns single session cost instead of total  
**Location:** `server.py:141`  
**Issue:**
```python
total_cost = db.query(SessionModel.current_cost).scalar() or 0.0
# This returns ONE session's cost, not sum of all
```

**Fix Applied:** Changed to use `func.sum()` to aggregate all session costs

---

### 7. Test Mock Signatures Don't Match Judge
**Impact:** Tests pass but don't actually test real code behavior  
**Location:** `test_router.py:52, 74`  
**Issue:**
```python
# Tests use 2-tuple: (0.3, "weak")
# Real judge returns 3-tuple: (0.3, "LOW", "reasoning")
```

**Fix Applied:** Updated test mocks to return correct 3-tuple format

---

## **MAJOR ISSUES (P1 - Logic Errors)**

### 8. Budget Check Race Condition
**Impact:** Multiple concurrent requests can exceed budget limits  
**Location:** `budget.py:54-76`  
**Issue:**
- `check_budget()` and `add_cost()` are separate operations
- Two requests can both pass budget check before either adds cost
- Example: Session has $9.50 used, limit $10. Two $5 requests both pass check (9.50 + 5 < 10), both execute, total becomes $19.50

**Fix Applied:** Added database-level locking using `with_for_update()` in budget check

---

### 9. Cycle Detection Timing Mismatch
**Impact:** Detects cycles with stale data, misses actual cycles  
**Location:** `router_logic.py:83`, `cycle_detector.py`  
**Issue:**
```python
# Line 83: Cycle check happens BEFORE LLM call
cycle_detected = cycle_detector.detect_cycle_with_prompt(prompt)

# But detect_cycle_with_prompt() uses last_response from PREVIOUS interaction
# It should check AFTER getting the new response
```

**Fix Applied:** 
- Keep pre-check for early exit if cycle detected
- Add post-check after LLM response to update cycle graph with current data
- Add clarifying comments

---

### 10. Unstable Prompt Hash
**Impact:** Same prompt gets different hashes across restarts, breaks historical analysis  
**Location:** `router_logic.py:160`  
**Issue:**
```python
prompt_hash=hash(prompt) % (2**32)
# Python's hash() is randomized per interpreter session for security
```

**Fix Applied:** Changed to use `hashlib.sha256()` for deterministic hashing

---

### 11. Anthropic Multiple System Messages
**Impact:** Only last system message kept, others silently dropped  
**Location:** `clients.py:167-175`  
**Issue:**
```python
if role == "system":
    system_prompt = content  # Overwrites previous system messages
```

**Fix Applied:** Concatenate multiple system messages with newline separator

---

### 12. Session ID Generation Creates New Sessions
**Impact:** Each request becomes separate session, breaks session tracking  
**Location:** `server.py:238-242`  
**Issue:**
```python
session_id = f"ip_{client_ip}_{uuid.uuid4().hex[:8]}"
# Generates NEW UUID every time, even for same IP
```

**Fix Applied:** Use deterministic session ID based on IP only (configurable via header)

---

### 13. Threshold Strict Mode Logic Inconsistency
**Impact:** Strict mode doesn't actually make router "stingier"  
**Location:** `threshold.py:61-67`, `router_logic.py:226-228`  
**Issue:**
- `is_strict_mode()` returns True when escalation rate > target
- But strict mode only downgrades decisions already above threshold
- Doesn't actually adjust the threshold itself
- Contradicts design intent of "5% rule"

**Fix Applied:** Modified strict mode to add penalty to complexity score (0.15) to make escalation harder

---

### 14. Database Async Context Manager Issue
**Impact:** Warning logs, potential connection leaks  
**Location:** `database.py:37-51`  
**Issue:**
```python
@contextmanager  # Synchronous
def get_db() -> SQLAlchemySession:
    # But called from async functions in router_logic.py
```

**Fix Applied:** Added `@contextmanager` decorator remains (SQLAlchemy sessions are sync), but documented proper async usage pattern

---

## **MINOR ISSUES (Code Quality)**

### 15. Cycle Detector Uses MD5 (Cryptographically Broken)
**Impact:** Potential hash collisions  
**Location:** `cycle_detector.py:39-54`  
**Issue:** MD5 is cryptographically broken, though for SimHash it's less critical

**Fix Applied:** Changed to SHA-256 for better collision resistance

---

### 16. Dockerfile WORKERS Variable Not Interpolated
**Impact:** Worker count always 2, can't be configured  
**Location:** `Dockerfile:61`  
**Issue:**
```dockerfile
"--workers", "${WORKERS:-2}"  # Shell expansion doesn't work in array CMD
```

**Fix Applied:** Changed to ENTRYPOINT with shell form to enable variable expansion

---

### 17. Docker Compose Volume Permissions
**Impact:** Permission denied errors on Linux  
**Location:** `docker-compose.yml:38-39`  
**Issue:**
```yaml
volumes:
  - ./data:/home/sentinel/app/data  # Host user != container sentinel user
```

**Fix Applied:** Changed to named volumes with proper permissions handling

---

## **MISSING COMPONENTS**

### 18. No Integration Tests
**Impact:** Can't verify end-to-end functionality  
**Status:** Documented in recommendations

### 19. No CI/CD Pipeline
**Impact:** No automated testing on commits  
**Status:** Documented in recommendations

### 20. No Pre-commit Hooks
**Impact:** Code quality tools not enforced  
**Status:** Documented in recommendations

---

## **TEST COVERAGE GAPS**

**Current Coverage:** ~20% (2 of 11 modules)

**Missing Tests:**
- `budget.py` - No tests for Module A
- `judge.py` - No tests for Module B
- `threshold.py` - No tests for Module C
- `cycle_detector.py` - No tests for Module D
- `clients.py` - No tests for LLM clients
- `database.py` - No tests for DB session management
- `logging_audit.py` - No tests for audit system
- `models.py` - No tests for ORM models
- `config.py` - No tests for settings

**Existing Test Issues:**
- `test_router.py` - Mocks use wrong return value format
- `test_server.py` - No actual HTTP integration tests
- No concurrent request tests (race conditions)
- No load tests for resource limits

---

## **SECURITY CONCERNS**

1. **CORS allows all origins** (`server.py:35`) - Should restrict in production
2. **MD5 hashing** (`cycle_detector.py`) - Cryptographically broken
3. **No secrets management** - API keys in environment variables (acceptable for local, needs vault for production)
4. **SQLite threading** - Limited concurrency, prone to locks
5. **No rate limiting** - Beyond budget control, no request rate limits
6. **No input validation** - Prompt size limits, message count limits

---

## **DEPLOYMENT CONCERNS**

1. **SQLite limitations** - Not suitable for high concurrency, consider PostgreSQL
2. **Single container** - No horizontal scaling, single point of failure
3. **No monitoring** - Prometheus metrics endpoint is placeholder
4. **No alerting** - Budget exceeded, errors need alerts
5. **Log rotation** - No log rotation configured, disk can fill up
6. **Resource limits** - 1 CPU / 512MB may be insufficient under load

---

## **RECOMMENDATIONS (Post-Fix)**

### Immediate (Before Production):
1. ✅ Fix all P0 issues (DONE)
2. ✅ Fix all P1 issues (DONE)
3. 🔲 Add integration tests for full request pipeline
4. 🔲 Add concurrent request tests
5. 🔲 Load test with expected traffic patterns
6. 🔲 Set up monitoring and alerting

### Short-term (Next Sprint):
1. 🔲 Add unit tests for all untested modules (budget, judge, threshold, cycle_detector, clients)
2. 🔲 Set up CI/CD pipeline (GitHub Actions)
3. 🔲 Add pre-commit hooks (black, mypy, pytest)
4. 🔲 Implement proper CORS configuration
5. 🔲 Add input validation middleware
6. 🔲 Configure log rotation

### Long-term (Production Hardening):
1. 🔲 Migrate to PostgreSQL for production deployments
2. 🔲 Add horizontal scaling support (external state store)
3. 🔲 Implement real Prometheus metrics
4. 🔲 Add distributed tracing (OpenTelemetry)
5. 🔲 Set up secrets management (AWS Secrets Manager, Vault)
6. 🔲 Implement request rate limiting
7. 🔲 Add WAF/DDoS protection

---

## **FIXES APPLIED - SUMMARY**

### Files Modified:
1. ✅ `requirements.txt` - Added pydantic-settings, gunicorn, updated versions
2. ✅ `router_logic.py` - Fixed class name, session_cost, prompt hash, cycle timing
3. ✅ `server.py` - Fixed metrics query, session ID generation
4. ✅ `Dockerfile` - Fixed health check, WORKERS variable interpolation
5. ✅ `docker-compose.yml` - Fixed volumes, added named volumes
6. ✅ `budget.py` - Added database locking for race condition
7. ✅ `cycle_detector.py` - Changed MD5 to SHA-256
8. ✅ `clients.py` - Fixed multiple system messages handling
9. ✅ `threshold.py` - Fixed strict mode to add complexity penalty
10. ✅ `test_router.py` - Fixed mock return value signatures
11. ✅ `database.py` - Added async usage documentation
12. ✅ `logging_audit.py` - Fixed method signature documentation

### Testing Status:
- ✅ Syntax validation (all files parse correctly)
- 🔲 Unit tests (need to run pytest after fixes)
- 🔲 Integration tests (need to create)
- 🔲 Docker build test (need to run docker build)
- 🔲 Docker compose test (need to run docker-compose up)

---

**Next Steps:**
1. Run `pytest tests/` to verify existing tests pass with fixes
2. Run `docker build -t sentinelrouter:latest .` to verify image builds
3. Run `docker-compose up` to verify container starts and health check passes
4. Create integration test script for end-to-end validation
5. Conduct load testing with concurrent requests
6. Review and implement security hardening recommendations

---

**Status:** 🟡 **BETA QUALITY** - Core bugs fixed, needs testing and hardening before production use.
