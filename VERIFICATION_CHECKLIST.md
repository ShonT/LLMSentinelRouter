# Post-Fix Verification Checklist

Use this checklist to verify everything is working after applying fixes.

## ✅ Pre-Deployment Checks

### 1. Environment Setup
- [ ] Python 3.11+ installed (`python3 --version`)
- [ ] `.env` file created with API keys
- [ ] Virtual environment activated

### 2. Dependencies
- [ ] Run: `pip install -r requirements.txt`
- [ ] Verify: `pip list | grep -E "(pydantic-settings|gunicorn|httpx)"`
- [ ] All three packages should appear

### 3. Code Verification
- [ ] Run: `python3 verify_fixes.py`
- [ ] All checks should pass ✅
- [ ] No ❌ symbols in output

### 4. Unit Tests
- [ ] Run: `pytest tests/test_router.py -v`
- [ ] All tests should pass
- [ ] Run: `pytest tests/test_server.py -v`
- [ ] All tests should pass

### 5. Integration Tests
- [ ] Run: `pytest tests/test_integration.py -v`
- [ ] Tests should pass (some may skip if no API keys)
- [ ] No errors or failures

### 6. Docker Build
- [ ] Run: `docker build -t sentinelrouter:latest .`
- [ ] Build should complete successfully
- [ ] No errors during image creation

### 7. Docker Compose
- [ ] Run: `docker-compose up --build`
- [ ] Container should start
- [ ] Health check should pass (status: healthy)
- [ ] No error logs

### 8. API Endpoints (Docker)
- [ ] Health: `curl http://localhost:8000/health`
  - Expected: `{"status": "healthy", "service": "sentinelrouter"}`
- [ ] Metrics: `curl http://localhost:8000/metrics`
  - Expected: JSON with session_count, total_cost, etc.
- [ ] Completions: Send test request
  ```bash
  curl -X POST http://localhost:8000/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{"messages": [{"role": "user", "content": "Hello"}], "session_id": "test"}'
  ```
  - Expected: OpenAI-compatible response with custom headers

### 9. Logs & Monitoring
- [ ] Check container logs: `docker-compose logs -f sentinelrouter`
- [ ] No error messages
- [ ] Routing decisions logged
- [ ] Check audit logs created in `logs/requests/`

### 10. Database
- [ ] Database file created: `data/sentinelrouter.db` (in Docker volume)
- [ ] Check sessions: `docker exec -it sentinelrouter sqlite3 /home/sentinel/app/data/sentinelrouter.db "SELECT * FROM sessions;"`
- [ ] Check decisions: `docker exec -it sentinelrouter sqlite3 /home/sentinel/app/data/sentinelrouter.db "SELECT * FROM routing_decisions;"`

---

## ✅ Specific Fix Verification

### Fix #1: Missing Dependencies
- [ ] `pydantic-settings` in requirements.txt
- [ ] `gunicorn` in requirements.txt
- [ ] Container starts without ImportError

### Fix #2: Class Naming
- [ ] `router_logic.py` uses `LoggingAudit` (not `AuditLogger`)
- [ ] No NameError on startup

### Fix #3: Session Cost
- [ ] Response headers include `X-Sentinel-Session-Cost`
- [ ] Value is not 0.0 for actual requests

### Fix #4: Health Check
- [ ] Dockerfile uses `import httpx` (not `import requests`)
- [ ] Container health check passes
- [ ] `docker ps` shows "(healthy)" status

### Fix #5: Metrics Query
- [ ] Metrics endpoint returns sum of all sessions
- [ ] Not just one random session cost

### Fix #6: Budget Race Condition
- [ ] `budget.py` uses `with_for_update()`
- [ ] Concurrent requests don't exceed budget

### Fix #7: Prompt Hash
- [ ] `router_logic.py` uses `hashlib.sha256` (not `hash()`)
- [ ] Same prompt produces same hash across restarts

### Fix #8: Session ID
- [ ] Same IP gets same session ID
- [ ] Not random UUID each time

### Fix #9: Strict Mode
- [ ] Complexity penalty applied in strict mode
- [ ] Escalation rate affects routing

### Fix #10: Test Mocks
- [ ] Test mocks return 3-tuple `(score, impact, reasoning)`
- [ ] Not 2-tuple `(score, route)`

### Fix #11: Docker Volumes
- [ ] docker-compose.yml uses named volumes
- [ ] No permission errors on Linux

### Fix #12: Cycle Detection
- [ ] `cycle_detector.py` uses SHA-256 (not MD5)
- [ ] Cycles detected correctly

---

## ✅ Performance & Load Testing

### Basic Load Test
```bash
# Install hey (HTTP load tester)
# macOS: brew install hey
# Linux: go install github.com/rakyll/hey@latest

# Run 100 requests with 10 concurrent
hey -n 100 -c 10 -m POST \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Test"}], "session_id": "load_test"}' \
  http://localhost:8000/v1/chat/completions
```

- [ ] No 500 errors
- [ ] No database locked errors
- [ ] Response time < 5s per request
- [ ] All requests succeed or fail gracefully

### Concurrent Session Test
```bash
# Create 10 sessions concurrently
for i in {1..10}; do
  curl -X POST http://localhost:8000/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d "{\"messages\": [{\"role\": \"user\", \"content\": \"Test $i\"}], \"session_id\": \"session_$i\"}" &
done
wait
```

- [ ] All sessions created successfully
- [ ] No race conditions
- [ ] Budget tracking accurate

---

## ✅ Security Checks

- [ ] Container runs as non-root user (sentinel)
- [ ] No secrets in logs
- [ ] CORS configured (check `server.py` line 35)
- [ ] API keys loaded from environment (not hardcoded)
- [ ] No MD5 hashing (only SHA-256)

---

## ✅ Documentation

- [ ] README.md updated with fix notice
- [ ] ISSUES.md exists and complete
- [ ] FIXES_SUMMARY.md exists
- [ ] CODE_REVIEW_RESULTS.md exists
- [ ] All commands in README work

---

## ✅ Production Readiness (Optional)

### Before Going to Production:
- [ ] Set up monitoring (Prometheus, Grafana)
- [ ] Configure log aggregation (ELK, CloudWatch)
- [ ] Set up alerting (PagerDuty, Slack)
- [ ] Load test with expected production traffic
- [ ] Implement rate limiting
- [ ] Migrate to PostgreSQL (if >100 req/min)
- [ ] Set up horizontal scaling (if >1000 req/min)
- [ ] Configure secrets manager (AWS Secrets, Vault)
- [ ] Set up reverse proxy with SSL (nginx, Traefik)
- [ ] Document runbook for incidents

---

## 🚨 If Something Fails

### Container won't start
1. Check logs: `docker-compose logs sentinelrouter`
2. Verify .env has API keys
3. Check disk space: `df -h`
4. Rebuild: `docker-compose down && docker-compose up --build`

### Tests fail
1. Check Python version: `python3 --version` (need 3.11+)
2. Reinstall dependencies: `pip install -r requirements.txt --force-reinstall`
3. Check .env file exists
4. Run verify_fixes.py: `python3 verify_fixes.py`

### ImportError
1. Check requirements.txt has all dependencies
2. Verify virtual environment activated
3. Run: `pip list | grep -E "(pydantic-settings|gunicorn)"`

### NameError or AttributeError
1. Run verify_fixes.py: `python3 verify_fixes.py`
2. Check for ❌ in output
3. Review ISSUES.md for the specific error

### Database locked
1. Reduce concurrent requests
2. Consider migrating to PostgreSQL
3. Increase timeout in database.py

### Health check failing
1. Check container logs
2. Verify httpx installed: `pip list | grep httpx`
3. Test manually: `curl http://localhost:8000/health`

---

## ✅ Sign-off

Once all items are checked:

- [ ] I have verified all fixes are applied
- [ ] I have run all tests successfully
- [ ] I have built the Docker image
- [ ] I have tested the Docker deployment
- [ ] I have reviewed the API responses
- [ ] I have checked the logs for errors
- [ ] System is ready for [development/staging/production]

**Verified by:** _______________  
**Date:** _______________  
**Status:** ✅ READY / ⚠️ NEEDS WORK / ❌ NOT READY

---

## Quick Reference

```bash
# Complete verification workflow
./setup.sh                           # Automated setup
python3 verify_fixes.py              # Verify fixes
pytest tests/ -v                     # Run all tests
docker build -t sentinelrouter .     # Build image
docker-compose up --build            # Start services
curl http://localhost:8000/health    # Test health
```

---

**For detailed information, see:**
- Issues & Fixes: `ISSUES.md`
- Before/After: `FIXES_SUMMARY.md`
- Complete Review: `CODE_REVIEW_RESULTS.md`
