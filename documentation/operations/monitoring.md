# SentinelRouter Metrics System - Implementation Summary

## ✅ Implementation Complete

The comprehensive metrics tracking system with web dashboard has been successfully integrated into SentinelRouter.

## 📊 Features Implemented

### 1. Metrics Collection (`sentinelrouter/sentinelrouter/metrics.py`)
- **File-based persistence**: JSONL format at `./data/metrics/metrics.jsonl`
- **200MB size limit with automatic rotation**
  - Archives old files with timestamp: `metrics_archive_YYYYMMDD_HHMMSS.jsonl`
  - Automatic cleanup when total size exceeds 200MB
- **Thread-safe operations** with Lock()
- **In-memory buffer** (deque with 1000 recent metrics)
- **Metrics tracked**:
  - Judge latency (ms, status)
  - Model latency (ms, status, route_type: weak/strong)
  - Fallback occurrences (judge/weak/strong)
  - Cycle detection events (session_id, hash_distance)
  - Tokens per second (tps, total_tokens)

### 2. Web Dashboard (`sentinelrouter/sentinelrouter/dashboard.py`)
- **FastAPI-based** standalone server
- **Port**: 8001 (runs alongside main API on 8000)
- **Auto-refresh**: Every 5 seconds
- **Charts**:
  - Judge Latency (bar chart: avg, min, max, p95, p99)
  - Model Latency (bar chart: weak/strong avg, p95)
  - Fallback Occurrences (doughnut chart)
  - Tokens Per Second (line chart: last 20 data points)
- **Stats Cards**: Total requests, avg latencies, cycle detections
- **Responsive design** with gradient background

### 3. Integration Points

#### Router Logic (`router_logic.py`)
- Records model latency for each request (weak/strong)
- Tracks tokens per second when available
- Records fallback events when backup models are used
- Records cycle detection events

#### Judge Registry (`judge_registry.py`)
- Records judge latency for each judgment call
- Tracks fallback to backup judges
- Records error status for failed judges

#### Server (`server.py`)
- Starts dashboard server in separate thread on port 8001
- Both servers run concurrently

## 🚀 Access

### Dashboard
- **URL**: http://localhost:8001
- **API Endpoint**: http://localhost:8001/api/metrics

### Main API
- **URL**: http://localhost:8000
- **Health**: http://localhost:8000/health
- **Chat**: http://localhost:8000/v1/chat/completions

## 📂 File Structure

```
sentinelrouter/
├── sentinelrouter/
│   ├── metrics.py          # Metrics collection module (NEW)
│   ├── dashboard.py        # Web dashboard server (NEW)
│   ├── router_logic.py     # Updated with metrics recording
│   ├── judge_registry.py   # Updated with metrics recording
│   └── server.py           # Updated to start dashboard
├── data/
│   └── metrics/
│       ├── metrics.jsonl                    # Current metrics
│       └── metrics_archive_*.jsonl          # Archived when rotated
├── docker-compose.yml      # Updated with port 8001
├── Dockerfile              # Updated with startup script
└── start_servers.sh        # Startup script for both servers (NEW)
```

## 🔧 Docker Configuration

### Ports Exposed
- `8000`: Main API server (gunicorn + uvicorn workers)
- `8001`: Metrics dashboard (uvicorn standalone)

### Startup Process
1. Dashboard server starts in background (pid 7)
2. Main API server starts with gunicorn (2 workers)
3. Both servers run concurrently

## 📈 Metrics Details

### Judge Latency Metrics
```json
{
  "type": "judge_latency",
  "timestamp": 1765456604.87,
  "judge_id": "deepseek-judge-backup1",
  "latency_ms": 425.3,
  "status": "success"
}
```

### Model Latency Metrics
```json
{
  "type": "model_latency",
  "timestamp": 1765456605.21,
  "model_id": "deepseek",
  "route_type": "weak",
  "latency_ms": 1250.7,
  "status": "success"
}
```

### Fallback Metrics
```json
{
  "type": "fallback",
  "timestamp": 1765456604.88,
  "fallback_type": "judge",
  "primary_id": "gemini-flash-live-primary",
  "backup_id": "deepseek-judge-backup1"
}
```

### Cycle Detection Metrics
```json
{
  "type": "cycle_detection",
  "timestamp": 1765456606.15,
  "session_id": "test-session-1",
  "hash_distance": 12345
}
```

### Tokens Per Second Metrics
```json
{
  "type": "tokens_per_second",
  "timestamp": 1765456605.21,
  "model_id": "deepseek",
  "route_type": "weak",
  "tps": 45.2,
  "total_tokens": 150
}
```

## 🧪 Testing

### Status Check
```bash
# Check both servers are running
curl http://localhost:8000/health  # Should return 200
curl http://localhost:8001/api/metrics  # Should return JSON with metrics
```

### Generate Test Data
Use the test script:
```bash
python3 test_metrics.py
```

Or make requests directly:
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Test question"}],
    "session_id": "test-session"
  }'
```

### View Metrics
1. Open browser to http://localhost:8001
2. Dashboard auto-refreshes every 5 seconds
3. View aggregated statistics and charts

## 📊 Dashboard Features

### Statistics Cards (Top Row)
1. **Total Requests**: Count of all requests processed
2. **Avg Judge Latency**: Average time for judge to evaluate (ms)
3. **Avg Weak Latency**: Average response time for weak models (ms)
4. **Avg Strong Latency**: Average response time for strong models (ms)
5. **Cycle Detections**: Number of cycles detected
6. **Avg Tokens/sec**: Average token generation rate

### Charts (Bottom Grid)
1. **Judge Latency Distribution**: Bar chart showing min, max, avg, p95, p99
2. **Model Latency Comparison**: Weak vs Strong model performance
3. **Fallback Analysis**: Pie chart of fallback occurrences by type
4. **Tokens Per Second Trend**: Line chart showing throughput over time

## 🔄 Metrics Rotation

- **Trigger**: When `metrics.jsonl` exceeds 200MB
- **Action**: 
  1. Rename current file to `metrics_archive_<timestamp>.jsonl`
  2. Create new empty `metrics.jsonl`
  3. Cleanup oldest archives if total exceeds 200MB

## 🛠️ Current Status

### ✅ Working
- Both servers running (8000, 8001)
- Metrics being collected and persisted
- Dashboard accessible and auto-refreshing
- File rotation configured
- Judge and model latency tracking
- Fallback tracking
- Cycle detection tracking

### ⚠️ Notes
- Gemini API hitting rate limits (429 errors) - expected with free tier
- DeepSeek API experiencing intermittent empty response errors
- System correctly falls back to default (0.1, LOW) when all judges fail
- Circuit breaker working - opens after 3 failures in 5 minutes
- Metrics recording even during errors (status="error")

## 🎯 Next Steps (Optional Enhancements)

1. **Add More Charts**: Cost tracking, error rates, session analysis
2. **Export Functionality**: Download metrics as CSV
3. **Alert System**: Notify when error rates exceed threshold
4. **Historical Analysis**: Compare performance across time periods
5. **Custom Dashboards**: Per-session or per-model views
6. **Metrics Aggregation**: Daily/weekly/monthly summaries

## 📝 Configuration

No additional configuration needed. The system automatically:
- Creates `data/metrics/` directory
- Initializes metrics collector on first import
- Starts dashboard server when main server starts
- Handles file rotation when size limit reached

## 🔍 Debugging

### Check Metrics File
```bash
docker exec sentinelrouter cat /home/sentinel/app/data/metrics/metrics.jsonl | jq
```

### Check Server Logs
```bash
docker logs sentinelrouter --tail 50
```

### Check Dashboard Status
```bash
curl http://localhost:8001/api/metrics | jq
```

## 🔬 Enhanced Routing Decision Tracking

**Added:** December 17, 2025

### Database-Level Tracking

Every routing decision now includes comprehensive token and latency tracking:

#### Routing Decisions Table
All requests are logged with:
- **Token Metrics**: `input_tokens`, `output_tokens`, `total_tokens`
- **Latency Metrics**: 
  - `request_latency_ms` - Total end-to-end request time
  - `model_latency_ms` - Time spent in LLM API call
  - `judge_latency_ms` - Judge invocation time (if used)

#### Escalation Traces Table
Strong model escalations include detailed trace data:
- **Request Info**: Preview of first 500 chars
- **Cycle Detection**: detected flag, hash distance, repetition count
- **Semantic Cache**: hit/miss, confidence, recommendation, call counts
- **Judge Results**: invoked flag, complexity score, impact scope, reasoning, latency
- **Routing Path**: initial decision, final decision, escalation reason
- **Model Used**: Final model that handled the request

### Query Examples

**Token Usage by Model:**
```sql
SELECT 
    model_used,
    COUNT(*) as requests,
    AVG(total_tokens) as avg_tokens,
    SUM(total_tokens) as total_tokens
FROM routing_decisions
GROUP BY model_used
ORDER BY total_tokens DESC;
```

**Latency Analysis:**
```sql
SELECT 
    model_used,
    AVG(request_latency_ms) as avg_request_ms,
    AVG(model_latency_ms) as avg_model_ms,
    AVG(judge_latency_ms) as avg_judge_ms
FROM routing_decisions
WHERE timestamp > datetime('now', '-1 hour')
GROUP BY model_used;
```

**Escalation Patterns:**
```sql
SELECT 
    cycle_detected,
    cache_hit,
    judge_invoked,
    initial_route_decision,
    final_route_decision,
    COUNT(*) as occurrences
FROM escalation_traces
GROUP BY cycle_detected, cache_hit, judge_invoked, 
         initial_route_decision, final_route_decision;
```

**Strong Model Escalation Reasons:**
```sql
SELECT 
    escalation_reason,
    COUNT(*) as count,
    AVG(judge_complexity_score) as avg_complexity
FROM escalation_traces
WHERE judge_invoked = 1
GROUP BY escalation_reason
ORDER BY count DESC;
```

### Migration

Run the migration script to add tracking to existing installations:

```bash
python3 scripts/migrate_enhanced_tracking.py
```

See `documentation/internal/enhanced-tracking-implementation.md` for full implementation details.

---

## ✅ Summary

The metrics system is fully operational with:
- ✅ 200MB file storage with auto-rotation
- ✅ Web dashboard on localhost:8001
- ✅ Real-time metrics collection
- ✅ Comprehensive tracking (latency, fallbacks, cycles, tokens/sec)
- ✅ **Enhanced database-level tracking (tokens, latencies, escalation traces)**
- ✅ Visual charts with auto-refresh
- ✅ Thread-safe operations
- ✅ Production-ready deployment

The dashboard is now available at **http://localhost:8001** and automatically updates every 5 seconds!
