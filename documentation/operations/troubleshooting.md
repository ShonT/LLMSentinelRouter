# Troubleshooting Guide

This guide covers common issues encountered when running SentinelRouter, their symptoms, causes, and step-by-step solutions.

## Quick Reference

| Symptom | Likely Cause | First Action |
|---------|--------------|--------------|
| Container won't start | Missing dependencies, port conflict | Check `docker-compose logs` |
| 500 Internal Server Error | Database locked, API key missing | Check server logs |
| Judge always fails | Gemini rate limits, circuit breaker open | Switch judge primary or wait |
| Budget exceeded unexpectedly | Race condition, misconfigured limits | Check budget.py locking |
| Slow response times | Judge latency, model fallbacks | Check dashboard metrics |
| No metrics in dashboard | Metrics file not loaded, API error | Verify `/api/metrics` endpoint |
| Session cost not tracking | Session ID generation issue | Check session headers |

## 1. Startup Issues

### 1.1 Container Fails to Start

**Symptoms:**
- Docker Compose exits immediately
- `docker ps` shows no running container
- Health check fails repeatedly

**Common Causes:**
1. **Missing dependencies**: `pydantic-settings` or `gunicorn` not installed
2. **Port conflict**: Port 8000 or 8001 already in use
3. **Permission issues**: Volume mounts with wrong user permissions
4. **Invalid API keys**: Missing or incorrect environment variables

**Solutions:**

#### Check Dependencies
```bash
# Verify requirements are installed
docker-compose build --no-cache
docker-compose run sentinelrouter python -c "import pydantic_settings, gunicorn"
```

#### Check Port Conflicts
```bash
# Check if ports are in use
lsof -i :8000
lsof -i :8001

# Change ports in docker-compose.yml if needed
sed -i '' 's/8000:8000/8080:8000/g' docker-compose.yml
```

#### Fix Permission Issues
```bash
# Reset volume permissions
sudo chown -R $USER:$USER ./data
sudo chown -R $USER:$USER ./logs
```

#### Verify Environment Variables
```bash
# Check .env file exists and has API keys
cat .env | grep -E "(DEEPSEEK|ANTHROPIC|GEMINI)_API_KEY"

# Test API keys directly
python -c "
import os
from sentinelrouter.clients import create_client
client = create_client('deepseek', os.getenv('DEEPSEEK_API_KEY'))
print('DeepSeek client created')
"
```

### 1.2 ImportError on Startup

**Symptoms:**
- `ModuleNotFoundError` or `ImportError` in logs
- Python cannot find sentinelrouter modules

**Causes:**
- Virtual environment not activated
- Package not installed in development mode
- PYTHONPATH incorrect

**Solutions:**
```bash
# Activate virtual environment
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows

# Install in development mode
pip install -e .

# Set PYTHONPATH
export PYTHONPATH=/path/to/sentinelrouter:$PYTHONPATH
```

## 2. Runtime Errors

### 2.1 500 Internal Server Error

**Symptoms:**
- HTTP 500 response from `/v1/chat/completions`
- Generic "Internal Server Error" message
- Server logs show traceback

**Common Causes and Fixes:**

#### Database Locked
```
sqlite3.OperationalError: database is locked
```

**Solution:**
```bash
# Increase timeout in database.py
# Change:
# engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
# To:
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False, "timeout": 30})

# Or reduce concurrent requests
# In server.py, add rate limiting
```

#### API Key Missing or Invalid
```
LLMClientError: 401 Unauthorized
```

**Solution:**
```bash
# Verify API keys are set
echo $DEEPSEEK_API_KEY
echo $ANTHROPIC_API_KEY

# Test API keys directly
curl -X POST https://api.deepseek.com/chat/completions \
  -H "Authorization: Bearer $DEEPSEEK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "deepseek-chat", "messages": [{"role": "user", "content": "Hello"}]}'
```

#### Circuit Breaker Open
```
Circuit breaker OPEN for gemini-primary: 3 failures in last 5 minutes
```

**Solution:**
- Wait for cooldown period (default 60 seconds)
- Switch to backup judge in configuration:
```json
"judge_config": {
  "model_order": ["deepseek-judge-backup1", "gemini-2.5-flash-lite-primary"]
}
```

### 2.2 Judge Always Fails

**Symptoms:**
- Every request shows "Judge failed, using backup"
- High judge latency (>30 seconds)
- Dashboard shows 100% fallback rate

**Causes:**
1. **Gemini rate limits**: Free tier has strict limits
2. **Network issues**: Firewall blocking Google APIs
3. **Invalid API key**: Gemini API key not configured

**Solutions:**

#### Check Gemini Status
```bash
# Test Gemini API directly
curl -X POST https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash-lite:generateContent \
  -H "Content-Type: application/json" \
  -H "x-goog-api-key: $GEMINI_API_KEY" \
  -d '{"contents": [{"parts": [{"text": "Hello"}]}]}'
```

#### Switch Primary Judge
```python
# In config/models_config.json, change judge order
"judge_config": {
  "model_order": [
    "deepseek-judge-backup1",  # Make DeepSeek primary
    "gemini-2.5-flash-lite-primary"
  ]
}
```

#### Disable Judge Temporarily
```bash
# Send request with judge disabled
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Sentinel-Use-Judge: false" \
  -d '{"messages": [{"role": "user", "content": "Hello"}]}'
```

### 2.3 Budget Exceeded Unexpectedly

**Symptoms:**
- Requests rejected with "Budget exceeded" before reaching limit
- Session cost jumps unexpectedly
- Multiple sessions show same cost

**Causes:**
1. **Race condition**: Concurrent requests bypass budget check
2. **Incorrect pricing**: Cost per token misconfigured
3. **Session mixing**: Different users sharing same session ID

**Solutions:**

#### Verify Budget Locking
```python
# Check budget.py has with_for_update()
# Line should look like:
with db.begin():
    session = db.query(SessionModel).filter(
        SessionModel.session_id == session_id
    ).with_for_update().first()
```

#### Check Pricing Configuration
```json
// In config/models_config.json, verify cost fields
"cost": {
  "per_call": 0.001,
  "per_token_input": 1.4e-07,  // $0.14 per million tokens
  "per_token_output": 2.8e-07  // $0.28 per million tokens
}
```

#### Use Unique Session IDs
```bash
# Generate unique session ID for each user
import uuid
session_id = str(uuid.uuid4())

# Or use IP-based session ID
import hashlib
import socket
ip = socket.gethostbyname(socket.gethostname())
session_id = hashlib.md5(ip.encode()).hexdigest()[:16]
```

### 2.4 Slow Response Times

**Symptoms:**
- Requests take >30 seconds
- Dashboard shows high latency
- Users experience timeouts

**Causes:**
1. **Judge latency**: Gemini/DeepSeek slow to respond
2. **Model fallbacks**: Multiple providers tried before success
3. **Network congestion**: High latency to API endpoints
4. **Database contention**: SQLite locking under load

**Solutions:**

#### Optimize Judge Configuration
```json
// Reduce judge timeout
"system_settings": {
  "judge_timeout_seconds": 15  // Default 30
}
```

#### Enable Semantic Cache
```python
# In router_logic.py, ensure cache is enabled
cache = SemanticCache()
if cache_result := cache.get(prompt_hash):
    return cache_result
```

#### Upgrade Infrastructure
```bash
# Increase Docker resources
# In docker-compose.yml
deploy:
  resources:
    limits:
      cpus: '2'
      memory: 1G
```

#### Use Connection Pooling
```python
# In database.py
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True
)
```

## 3. Dashboard Issues

### 3.1 Dashboard Shows No Data

**Symptoms:**
- Dashboard loads but shows zeros
- Charts empty despite traffic
- "No metrics available" message

**Causes:**
1. Metrics file not being written
2. API endpoint returning empty data
3. Dashboard JavaScript errors

**Solutions:**

#### Check Metrics File
```bash
# Verify metrics file exists and has data
ls -la logs/metrics/
tail -n 10 logs/metrics/metrics_2025-12-14.jsonl

# Check file permissions
chmod 644 logs/metrics/*.jsonl
```

#### Test Metrics API
```bash
# Call metrics API directly
curl http://localhost:8001/api/metrics

# Expected output:
# {"total_metrics": 42, "judge_latency": {...}}
```

#### Check Dashboard Logs
```bash
# View dashboard server logs
docker-compose logs dashboard

# Check browser console for JavaScript errors
# Press F12 → Console
```

### 3.2 Auto-Refresh Not Working

**Symptoms:**
- Dashboard shows stale data
- Manual refresh required
- "Last updated" timestamp old

**Causes:**
1. JavaScript auto-refresh disabled
2. Browser caching responses
3. API returning cached data

**Solutions:**

#### Verify JavaScript Configuration
```javascript
// In dashboard static/js/dashboard.js
// Should have:
setInterval(fetchMetrics, 5000);  // Refresh every 5 seconds
```

#### Disable Browser Cache
```python
# In dashboard.py, add cache control headers
@app.get("/api/metrics")
async def get_metrics():
    response = JSONResponse(content=metrics_data)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response
```

#### Force Dashboard Refresh
```bash
# Clear browser cache
# Chrome: Ctrl+Shift+R (hard refresh)
# Or open dashboard with cache busting:
open "http://localhost:8001?t=$(date +%s)"
```

## 4. Configuration Issues

### 4.1 Configuration Not Loading

**Symptoms:**
- Default values used instead of config
- Changes to models_config.json not taking effect
- "Invalid configuration" errors

**Causes:**
1. Configuration file not found
2. JSON syntax error
3. Pydantic validation failure

**Solutions:**

#### Validate Configuration
```bash
# Validate JSON syntax
python -m json.tool config/models_config.json

# Validate with Pydantic
python -c "
from sentinelrouter.schemas.config_models import UnifiedConfig
import json
with open('config/models_config.json') as f:
    config = UnifiedConfig(**json.load(f))
print('Configuration valid')
"
```

#### Check File Paths
```python
# Verify config.py loads correct path
import os
config_path = os.getenv('CONFIG_PATH', 'config/models_config.json')
print(f"Loading config from: {config_path}")
```

### 4.2 Environment Variables Not Recognized

**Symptoms:**
- API keys not found despite being in .env
- Default values used instead of environment
- "API key missing" errors

**Causes:**
1. .env file not in correct location
2. Variable names don't match
3. Docker not loading .env

**Solutions:**

#### Verify .env File
```bash
# Check .env file location and content
pwd
cat .env

# Load .env manually
export $(cat .env | xargs)
echo $DEEPSEEK_API_KEY
```

#### Docker Compose Environment
```yaml
# In docker-compose.yml, ensure env_file is specified
services:
  sentinelrouter:
    env_file:
      - .env
```

## 5. Database Issues

### 5.1 Database Corruption

**Symptoms:**
- "Database disk image is malformed"
- Queries return inconsistent results
- SQLite errors on simple queries

**Solutions:**

#### Backup and Recreate
```bash
# Backup existing database
cp data/sentinelrouter.db data/sentinelrouter.db.backup

# Recreate database
rm data/sentinelrouter.db
python -c "from sentinelrouter.database import init_db; init_db()"

# Or use migration script
python scripts/migrate_sqlite_to_json.py
```

#### Repair SQLite Database
```bash
# Use SQLite repair tool
sqlite3 data/sentinelrouter.db ".dump" | sqlite3 data/sentinelrouter.new.db
mv data/sentinelrouter.new.db data/sentinelrouter.db
```

### 5.2 Migration Issues

**Symptoms:**
- "Table already exists" errors
- Missing columns after upgrade
- Data not migrated correctly

**Solutions:**

#### Run Migration Scripts
```bash
# Run all migration scripts in order
python scripts/migrate_sqlite_to_json.py
python scripts/migrate_config.py
python scripts/migrate_add_session_tier.py
```

#### Manual Migration
```sql
-- Check current schema
sqlite3 data/sentinelrouter.db ".schema"

-- Compare with expected schema in database.py
-- Add missing columns manually
ALTER TABLE sessions ADD COLUMN tier VARCHAR(10) DEFAULT 'free';
```

## 6. Performance Issues

### 6.1 High Memory Usage

**Symptoms:**
- Container killed due to OOM
- Slow response under load
- Memory usage >80% in dashboard

**Solutions:**

#### Increase Memory Limits
```yaml
# In docker-compose.yml
services:
  sentinelrouter:
    deploy:
      resources:
        limits:
          memory: 1G
        reservations:
          memory: 512M
```

#### Optimize Python Memory
```python
# In server.py, use streaming responses
@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    # Use streaming to avoid holding large responses in memory
    async def generate():
        yield data
    return StreamingResponse(generate())
```

#### Monitor Memory Usage
```bash
# Check container memory
docker stats sentinelrouter

# Profile Python memory
pip install memory_profiler
python -m memory_profiler sentinelrouter/server.py
```

### 6.2 High CPU Usage

**Symptoms:**
- Slow response times
- System lagging
- CPU >80% in dashboard

**Solutions:**

#### Optimize Expensive Operations
```python
# Cache judge results
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_judge_complexity(prompt: str) -> float:
    # Expensive LLM call
    pass
```

#### Reduce Logging Overhead
```python
# Use lazy logging
logger.debug("Complex prompt: %s", prompt)  # Good
logger.debug(f"Complex prompt: {prompt}")   # Bad (evaluated always)
```

#### Scale Horizontally
```yaml
# In docker-compose.yml, add replicas
services:
  sentinelrouter:
    deploy:
      replicas: 3
    environment:
      - WORKERS=1
```

## 7. Network Issues

### 7.1 API Endpoints Unreachable

**Symptoms:**
- "Connection refused" errors
- Timeout when accessing endpoints
- Intermittent connectivity

**Solutions:**

#### Check Firewall Rules
```bash
# Verify ports are open
sudo ufw status
sudo ufw allow 8000/tcp
sudo ufw allow 8001/tcp
```

#### Test Network Connectivity
```bash
# From host to container
docker exec sentinelrouter curl http://localhost:8000/health

# From external machine
telnet your-server-ip 8000
```

#### Configure Reverse Proxy
```nginx
# Nginx configuration
server {
    listen 80;
    server_name sentinel.yourdomain.com;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
    }
    
    location /dashboard {
        proxy_pass http://localhost:8001;
        proxy_set_header Host $host;
    }
}
```

## Emergency Procedures

### Immediate Restart
```bash
# Full system restart
docker-compose down
docker system prune -af  # WARNING: removes all Docker data
docker-compose up --build
```

### Rollback to Previous Version
```bash
# Revert to previous Git commit
git log --oneline -5
git checkout <previous-commit-hash>
docker-compose up --build
```

### Disable Problematic Features
```python
# In config/models_config.json, disable features temporarily
"system_settings": {
  "enable_judge": false,
  "enable_cache": true,
  "enable_cycle_detection": false
}
```

## Getting Help

### Collect Diagnostics
```bash
# Run diagnostics script
./scripts/diagnostics.sh

# Or collect manually
docker-compose logs --tail=100 > logs/docker.log
curl http://localhost:8000/health > logs/health.json
curl http://localhost:8001/api/metrics > logs/metrics.json
```

### Open an Issue
Include the following information:
1. **Environment**: `uname -a`, `docker version`, `python --version`
2. **Configuration**: Redacted config/models_config.json
3. **Logs**: Last 100 lines from docker-compose logs
4. **Steps to Reproduce**: Exact commands that trigger the issue
5. **Expected vs Actual Behavior**: What you expected vs what happened

### Community Support
- Check existing issues in GitHub
- Search for similar problems in documentation
- Ask in project discussions (if available)

---

**Remember**: Always backup your configuration and database before making significant changes. Test changes in a staging environment before applying to production.