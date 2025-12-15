# Issue: Enhanced Request Latency Dashboard with 4-Hour Timeline

**Label:** `enhancement`, `dashboard`, `metrics`  
**Priority:** High  
**Estimated Effort:** 4-6 hours

---

## Overview

Enhance the latency trends graph in the dashboard to provide comprehensive visibility into system performance over a 4-hour sliding window with per-minute granularity and interactive toggle functionality.

---

## Current State

### Existing Implementation
- **Graph Title:** "📈 Latency Trends (Last 50 Requests)"
- **Time Window:** Fixed at last 50 requests (request-count based)
- **Granularity:** Per-request (indexed 1-50)
- **Lines Displayed:** 3 lines (Judge, Weak Model, Strong Model)
- **Interaction:** No toggle capability
- **Missing Metric:** Overall request latency not tracked

### Problems
1. ❌ Request-count based window doesn't show time-based patterns
2. ❌ 50 requests may represent 5 minutes or 5 hours depending on traffic
3. ❌ No overall end-to-end latency visibility
4. ❌ Cannot hide/show specific lines to focus on particular metrics
5. ❌ Per-request granularity makes high-traffic periods unreadable

---

## Required Changes

### 1. Add Overall Request Latency Tracking

**Requirement:** Track end-to-end latency for **successful requests only**

#### Why Only Successful Requests?
- Failed requests don't represent normal system performance
- Including failures would skew averages
- Failures are tracked separately in error metrics

#### Implementation Location
**File:** `sentinelrouter/sentinelrouter/router_logic.py`  
**Method:** `Router.route()`

```python
async def route(
    self,
    session_id: str,
    prompt: str,
    messages: list,
    # ... other params
) -> Dict[str, Any]:
    route_start = time.time()  # Start timing
    
    try:
        # ... existing routing logic ...
        
        # After successful response (line ~571)
        if response and response.content:
            route_end = time.time()
            overall_latency_ms = (route_end - route_start) * 1000
            
            # Record overall latency
            metrics.record_event("overall_request_latency", {
                "session_id": session_id,
                "request_id": request_id,
                "latency_ms": overall_latency_ms,
                "model_used": model_used,
                "route_type": route_decision,
                "timestamp": datetime.utcnow().isoformat()
            })
            
        # ... existing response return ...
        
    except Exception as e:
        # Failed request - do NOT record overall latency
        logger.error(f"Request failed: {e}")
        raise
```

**Lines to Modify:** ~571-580 (after response validation, before return)

---

### 2. Dashboard Backend Changes

#### 2.1 Add Utility Functions

**File:** `sentinelrouter/sentinelrouter/dashboard.py`  
**Location:** After imports, before endpoint definitions (~line 50)

```python
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

def aggregate_metrics_by_minute(
    events: List[Dict],
    event_type: str,
    metric_key: str = "latency_ms",
    time_window_hours: int = 4
) -> Dict[int, float]:
    """
    Aggregate metric values by minute for a specific event type.
    
    Args:
        events: List of all metric events
        event_type: Type of event to filter (e.g., 'judge_latency')
        metric_key: Key to extract from event data (default: 'latency_ms')
        time_window_hours: Max time window to consider (default: 4)
    
    Returns:
        Dict mapping minute offset to average value
        Example: {0: 150.5, 1: 142.3, 2: 155.7, ...}
        Where key 0 = most recent minute, 1 = 1 minute ago, etc.
    """
    now = datetime.utcnow()
    cutoff_time = now - timedelta(hours=time_window_hours)
    
    # Filter for event type and time window
    filtered_events = [
        e for e in events 
        if e.get("type") == event_type
    ]
    
    # Group by minute
    minute_buckets = defaultdict(list)
    for event in filtered_events:
        timestamp = event.get("timestamp")
        if timestamp is None:
            continue
            
        # timestamp is a float (unix time)
        event_dt = datetime.fromtimestamp(timestamp)
            
        if event_dt < cutoff_time:
            continue
            
        # Calculate minute offset (0 = current minute, 1 = 1 minute ago, etc.)
        minute_offset = int((now - event_dt).total_seconds() / 60)
        
        value = event.get(metric_key)
        if value is not None:
            minute_buckets[minute_offset].append(value)
    
    # Calculate averages per minute
    return {
        minute: sum(values) / len(values)
        for minute, values in minute_buckets.items()
    }


def prepare_line_chart_data(
    minute_data: Dict[int, float],
    max_minutes: int = 240
) -> Tuple[List[str], List[Optional[float]]]:
    """
    Convert minute bucket data to Chart.js format.
    
    Args:
        minute_data: Dict of minute offset -> average value
        max_minutes: Maximum minutes to display (default: 240 for 4 hours)
    
    Returns:
        Tuple of (labels, data):
        - labels: ["240m", "239m", ..., "1m", "0m"] (time ago labels)
        - data: [150.5, 142.3, None, 155.7, ...] (None for missing data points)
    """
    # Create labels from max_minutes down to 0 (reverse chronological)
    labels = [f"{minute}m" for minute in range(max_minutes, -1, -1)]
    
    # Map data, using None for missing minutes
    data = [
        minute_data.get(minute)  # Returns None if minute not in dict
        for minute in range(max_minutes, -1, -1)
    ]
    
    return labels, data
```

**Lines to Add:** ~50-120 (new utility section)

---

#### 2.2 Update Metrics Endpoint

**File:** `sentinelrouter/sentinelrouter/dashboard.py`  
**Method:** `get_dashboard_metrics()`  
**Lines:** ~1359-1469 (entire method needs updates)

```python
@dashboard_app.get("/api/dashboard/metrics")
async def get_dashboard_metrics(db: Session = Depends(get_dbsession)):
    """
    Returns comprehensive dashboard metrics including latency trends.
    """
    from .metrics import get_metrics_collector
    
    # Get metrics from collector
    collector = get_metrics_collector()
    stats = collector.get_aggregated_stats()
    
    # Get more events to cover 4-hour window
    recent_metrics = collector.get_recent_metrics(limit=10000)
    
    # Filter for successful latency events only (status != 'error')
    successful_latency_metrics = [
        m for m in recent_metrics 
        if m.get("type") in [
            "judge_latency", 
            "weak_model_latency", 
            "strong_model_latency",
            "overall_request_latency"
        ]
        and m.get("status") != "error"
    ]
    
    # Aggregate by minute for each metric type
    time_window_hours = 4
    
    judge_by_minute = aggregate_metrics_by_minute(
        recent_metrics,
        "judge_latency",
        "latency_ms",
        time_window_hours
    )
    
    weak_model_by_minute = aggregate_metrics_by_minute(
        recent_metrics,
        "weak_model_latency",
        "latency_ms",
        time_window_hours
    )
    
    strong_model_by_minute = aggregate_metrics_by_minute(
        recent_metrics,
        "strong_model_latency",
        "latency_ms",
        time_window_hours
    )
    
    overall_by_minute = aggregate_metrics_by_minute(
        recent_metrics,
        "overall_request_latency",
        "latency_ms",
        time_window_hours
    )
    
    # Prepare Chart.js data (240 minutes = 4 hours)
    labels, judge_data = prepare_line_chart_data(judge_by_minute, max_minutes=240)
    _, weak_data = prepare_line_chart_data(weak_model_by_minute, max_minutes=240)
    _, strong_data = prepare_line_chart_data(strong_model_by_minute, max_minutes=240)
    _, overall_data = prepare_line_chart_data(overall_by_minute, max_minutes=240)
    
    # ... existing metrics calculations ...
    
    return JSONResponse({
        # ... existing metrics ...
        
        "latency_series": {
            "labels": labels,  # ["240m", "239m", ..., "1m", "0m"]
            "judge": judge_data,
            "weak": weak_data,
            "strong": strong_data,
            "overall": overall_data
        }
    })
```

**Lines to Modify:** Replace latency processing section (~1370-1407)

---

### 3. Dashboard Frontend Changes

#### 3.1 Update Chart Rendering

**File:** `sentinelrouter/sentinelrouter/dashboard.py`  
**Section:** HTML template embedded JavaScript  
**Lines:** ~804-875 (latency chart section)

```javascript
// Latency Trends Chart with Toggle Functionality
let latencyChart = null;

function updateLatencyChart(series) {
    const ctx = document.getElementById('latencyChart');
    if (!ctx) return;
    
    if (latencyChart) {
        latencyChart.destroy();
    }
    
    const labels = series?.labels || [];
    const judgeData = series?.judge || [];
    const weakData = series?.weak || [];
    const strongData = series?.strong || [];
    const overallData = series?.overall || [];
    
    latencyChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Judge Latency',
                    data: judgeData,
                    borderColor: '#f59e0b',
                    backgroundColor: 'rgba(245, 158, 11, 0.1)',
                    tension: 0.4,
                    fill: false,
                    spanGaps: true
                },
                {
                    label: 'Weak Model Latency',
                    data: weakData,
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    tension: 0.4,
                    fill: false,
                    spanGaps: true
                },
                {
                    label: 'Strong Model Latency',
                    data: strongData,
                    borderColor: '#ef4444',
                    backgroundColor: 'rgba(239, 68, 68, 0.1)',
                    tension: 0.4,
                    fill: false,
                    spanGaps: true
                },
                {
                    label: 'Overall Request Latency',
                    data: overallData,
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    tension: 0.4,
                    fill: false,
                    spanGaps: true
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    onClick: (e, legendItem, legend) => {
                        // Toggle visibility when clicking legend
                        const index = legendItem.datasetIndex;
                        const chart = legend.chart;
                        const meta = chart.getDatasetMeta(index);
                        
                        // Toggle hidden state
                        meta.hidden = meta.hidden === null 
                            ? !chart.data.datasets[index].hidden 
                            : null;
                        
                        // Update chart
                        chart.update();
                    },
                    labels: {
                        usePointStyle: true,
                        padding: 15,
                        font: {
                            size: 12
                        }
                    }
                },
                title: {
                    display: true,
                    text: '📈 Latency Trends (Last 4 Hours)',
                    font: {
                        size: 16,
                        weight: 'bold'
                    }
                },
                tooltip: {
                    callbacks: {
                        title: function(context) {
                            return `${context[0].label} ago`;
                        },
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            if (context.parsed.y !== null) {
                                label += context.parsed.y.toFixed(2) + ' ms';
                            } else {
                                label += 'No data';
                            }
                            return label;
                        }
                    }
                }
            },
            scales: {
                x: {
                    display: true,
                    title: {
                        display: true,
                        text: 'Time (minutes ago)',
                        font: {
                            size: 14
                        }
                    },
                    ticks: {
                        maxTicksLimit: 12,
                        callback: function(value, index, ticks) {
                            // Show cleaner labels (every 20 minutes)
                            const minute = 240 - index;
                            if (minute % 20 === 0) {
                                return `${minute}m`;
                            }
                            return '';
                        }
                    }
                },
                y: {
                    display: true,
                    title: {
                        display: true,
                        text: 'Latency (ms)',
                        font: {
                            size: 14
                        }
                    },
                    beginAtZero: true,
                    ticks: {
                        callback: function(value) {
                            return value.toFixed(0) + ' ms';
                        }
                    }
                }
            }
        }
    });
}
```

**Lines to Replace:** ~804-875 (entire latency chart section)

#### 3.2 Update HTML Title

**File:** `sentinelrouter/sentinelrouter/dashboard.py`  
**Line:** ~573

```html
<div class="chart-title">📈 Latency Trends (Last 4 Hours)</div>
```

**Replace:** Change "Last 50 Requests" to "Last 4 Hours"

---

## Testing Requirements

### Unit Tests

**File:** `tests/unit/test_dashboard_latency.py` (NEW)

```python
import pytest
from datetime import datetime, timedelta
from sentinelrouter.dashboard import (
    aggregate_metrics_by_minute,
    prepare_line_chart_data
)

class TestLatencyAggregation:
    def test_aggregate_metrics_by_minute_basic(self):
        """Test basic minute aggregation"""
        now = datetime.utcnow()
        events = [
            {
                "type": "judge_latency",
                "timestamp": now.timestamp(),
                "latency_ms": 100
            },
            {
                "type": "judge_latency",
                "timestamp": now.timestamp(),
                "latency_ms": 200
            }
        ]
        
        result = aggregate_metrics_by_minute(events, "judge_latency")
        
        assert 0 in result  # Current minute
        assert result[0] == 150.0  # Average of 100 and 200
    
    def test_aggregate_metrics_ignores_old_events(self):
        """Test that events older than time window are ignored"""
        now = datetime.utcnow()
        old_time = now - timedelta(hours=5)
        
        events = [
            {
                "type": "judge_latency",
                "timestamp": old_time.timestamp(),
                "latency_ms": 999
            },
            {
                "type": "judge_latency",
                "timestamp": now.timestamp(),
                "latency_ms": 100
            }
        ]
        
        result = aggregate_metrics_by_minute(events, "judge_latency", time_window_hours=4)
        
        assert 0 in result
        assert result[0] == 100.0  # Old event ignored
    
    def test_aggregate_metrics_by_minute_groups_correctly(self):
        """Test that events are grouped by minute offset"""
        now = datetime.utcnow()
        one_min_ago = now - timedelta(minutes=1)
        two_min_ago = now - timedelta(minutes=2)
        
        events = [
            {
                "type": "weak_model_latency",
                "timestamp": now.timestamp(),
                "latency_ms": 100
            },
            {
                "type": "weak_model_latency",
                "timestamp": one_min_ago.timestamp(),
                "latency_ms": 150
            },
            {
                "type": "weak_model_latency",
                "timestamp": one_min_ago.timestamp(),
                "latency_ms": 250
            },
            {
                "type": "weak_model_latency",
                "timestamp": two_min_ago.timestamp(),
                "latency_ms": 300
            }
        ]
        
        result = aggregate_metrics_by_minute(events, "weak_model_latency")
        
        assert result[0] == 100.0  # Current minute
        assert result[1] == 200.0  # 1 minute ago: avg(150, 250)
        assert result[2] == 300.0  # 2 minutes ago
    
    def test_prepare_line_chart_data(self):
        """Test Chart.js data preparation"""
        minute_data = {
            0: 100.0,
            1: 150.0,
            3: 200.0  # Missing minute 2
        }
        
        labels, data = prepare_line_chart_data(minute_data, max_minutes=5)
        
        assert labels == ["5m", "4m", "3m", "2m", "1m", "0m"]
        assert data == [None, None, 200.0, None, 150.0, 100.0]
    
    def test_aggregate_filters_by_event_type(self):
        """Test that only specified event type is aggregated"""
        now = datetime.utcnow()
        events = [
            {
                "type": "judge_latency",
                "timestamp": now.timestamp(),
                "latency_ms": 100
            },
            {
                "type": "weak_model_latency",
                "timestamp": now.timestamp(),
                "latency_ms": 999
            }
        ]
        
        result = aggregate_metrics_by_minute(events, "judge_latency")
        
        assert result[0] == 100.0  # Only judge latency included
```

### Integration Tests

**File:** `tests/integration/test_latency_dashboard_integration.py` (NEW)

```python
import pytest
import asyncio
from datetime import datetime
from sentinelrouter.router_logic import Router
from sentinelrouter.metrics import get_metrics_collector

@pytest.mark.asyncio
async def test_overall_latency_recorded_on_success(router_instance):
    """Test that overall latency is recorded for successful requests"""
    session_id = "test-session"
    prompt = "Hello"
    messages = [{"role": "user", "content": prompt}]
    
    # Make successful request
    result = await router_instance.route(
        session_id=session_id,
        prompt=prompt,
        messages=messages
    )
    
    # Check that overall_request_latency event was recorded
    collector = get_metrics_collector()
    events = collector.get_recent_metrics(limit=100)
    overall_events = [
        e for e in events 
        if e.get("type") == "overall_request_latency"
    ]
    
    assert len(overall_events) > 0
    assert "latency_ms" in overall_events[0]
    assert overall_events[0]["latency_ms"] > 0

@pytest.mark.asyncio
async def test_overall_latency_not_recorded_on_failure(router_instance):
    """Test that overall latency is NOT recorded for failed requests"""
    session_id = "test-session"
    prompt = "This will fail"
    messages = [{"role": "user", "content": prompt}]
    
    # Force all models to fail (mock implementation)
    with pytest.raises(Exception):
        await router_instance.route(
            session_id=session_id,
            prompt=prompt,
            messages=messages
        )
    
    # Check that no overall_request_latency event was recorded for this session
    collector = get_metrics_collector()
    events = collector.get_recent_metrics(limit=100)
    overall_events = [
        e for e in events 
        if e.get("type") == "overall_request_latency"
    ]
    
    # Should not have increased
    assert len(overall_events) == 0 or overall_events[-1].get("session_id") != session_id
```

---

## Acceptance Criteria

### Functional Requirements

- [ ] Overall request latency is tracked and recorded
- [ ] Only successful requests contribute to latency metrics
- [ ] Failed requests do NOT create latency data points
- [ ] Dashboard displays 4-hour sliding window (not request-count based)
- [ ] Graph shows per-minute granularity with averaging
- [ ] Four separate lines are displayed:
  - [ ] Judge latency (amber #f59e0b)
  - [ ] Weak model latency (green #10b981)
  - [ ] Strong model latency (red #ef4444)
  - [ ] Overall request latency (blue #3b82f6)
- [ ] Chart title reads "📈 Latency Trends (Last 4 Hours)"
- [ ] X-axis shows time in minutes (240m to 0m)
- [ ] Y-axis shows latency in milliseconds
- [ ] Clicking legend items toggles line visibility
- [ ] Hidden lines remain hidden during dashboard refresh
- [ ] Missing data points show as gaps (not zero)
- [ ] Chart uses `spanGaps: true` to connect across nulls

### Non-Functional Requirements

- [ ] Dashboard updates every 5 seconds
- [ ] Chart rendering is smooth (no flicker)
- [ ] Memory usage acceptable with 10,000 events
- [ ] API endpoint responds within 200ms
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] Code follows existing style conventions

---

## Implementation Checklist

### Step 1: Add Overall Latency Tracking
- [ ] Modify `sentinelrouter/router_logic.py` line ~100
- [ ] Add `route_start = time.time()` at method start
- [ ] Add overall latency recording in success block (line ~571)
- [ ] Ensure recording ONLY happens for successful requests
- [ ] Test manually with curl request

### Step 2: Add Dashboard Utilities
- [ ] Add `aggregate_metrics_by_minute()` function to `dashboard.py`
- [ ] Add `prepare_line_chart_data()` function to `dashboard.py`
- [ ] Add unit tests for both utility functions
- [ ] Verify utilities handle edge cases (empty data, old events)

### Step 3: Update Dashboard Backend
- [ ] Modify `get_dashboard_metrics()` endpoint
- [ ] Change from last-50-requests to 4-hour time window
- [ ] Add overall latency to response structure
- [ ] Add proper filtering for successful events only
- [ ] Test endpoint with curl/Postman

### Step 4: Update Dashboard Frontend
- [ ] Replace latency chart JavaScript code
- [ ] Update chart title to "Last 4 Hours"
- [ ] Add 4th dataset for overall latency
- [ ] Implement legend click handler for toggle
- [ ] Update X-axis to show minutes
- [ ] Add `spanGaps: true` to all datasets
- [ ] Test in browser with various screen sizes

### Step 5: Testing
- [ ] Write unit tests for utility functions
- [ ] Write integration tests for latency recording
- [ ] Write integration tests for dashboard endpoint
- [ ] Run full test suite
- [ ] Manual testing in production-like environment

### Step 6: Documentation
- [ ] Update README with new metric description
- [ ] Add screenshots of new graph to documentation
- [ ] Document toggle functionality
- [ ] Update metrics documentation

### Step 7: Deployment
- [ ] Build Docker image
- [ ] Test in staging environment
- [ ] Deploy to production
- [ ] Monitor for errors
- [ ] Verify graph displays correctly

---

## Rollback Plan

If issues arise after deployment:

1. **Immediate Rollback:**
   - Revert to previous Docker image
   - Dashboard will show old 50-request view
   - No data loss (metrics still collected)

2. **Partial Rollback:**
   - Comment out overall latency recording in `router_logic.py`
   - Keep dashboard utilities (no harm)
   - Revert frontend changes only

3. **Data Issues:**
   - If metrics corrupted, restart container
   - Metrics are in-memory, restart clears them
   - No persistent data affected

---

## Dependencies

### External Libraries
- Chart.js (already included)
- No new dependencies required

### Internal Components
- Metrics module (existing)
- StateManager (existing)
- Router (existing)
- Dashboard (existing)

---

## Timeline Estimate

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Step 1: Latency Tracking | 1 hour | None |
| Step 2: Utilities | 1 hour | Step 1 complete |
| Step 3: Backend | 1 hour | Step 2 complete |
| Step 4: Frontend | 1.5 hours | Step 3 complete |
| Step 5: Testing | 1 hour | Steps 1-4 complete |
| Step 6: Documentation | 0.5 hours | Step 5 complete |
| Step 7: Deployment | 0.5 hours | All steps complete |
| **Total** | **6.5 hours** | Sequential |

---

## Success Metrics

### Before Implementation
- Latency visibility: Last 50 requests only
- Time context: Unknown
- User feedback: "Can't see patterns over time"
- Toggle functionality: None

### After Implementation
- Latency visibility: Full 4-hour sliding window
- Time context: Per-minute granularity
- User feedback: "Can identify performance trends"
- Toggle functionality: Interactive legend

### Quantitative Metrics
- Dashboard load time: < 500ms (target: < 200ms)
- Chart render time: < 100ms
- Memory usage: < 50MB for 10k events
- API response time: < 200ms (target: < 100ms)

---

## Related Issues

- [ ] Dashboard performance optimization
- [ ] Metrics retention policy (related to 4-hour window)
- [ ] Export metrics to CSV feature

---

## Notes

- This change is **backward compatible** - no breaking changes
- Existing metrics endpoints remain unchanged
- Old 50-request data still available if needed
- Can be feature-flagged if rollout needs to be gradual
