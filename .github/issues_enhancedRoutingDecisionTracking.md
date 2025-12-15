# Enhanced Routing Decision and Escalation Tracking

## Overview

This issue covers enhancements to improve visibility and debugging capabilities for routing decisions and strong model escalations by adding comprehensive trace information and token/latency metrics.

**Created:** December 14, 2025  
**Priority:** High  
**Estimated Time:** 8-10 hours  
**Status:** Planning

---

## Problem Statement

### Current State

The system tracks routing decisions and escalations but lacks:

1. **Strong Model Escalations** - Missing trace information:
   - No record of which components were consulted (cycle detector, semantic cache, judge)
   - No visibility into cache hit/miss status and confidence scores
   - No judge results preserved with escalation
   - No full request flow trace

2. **All Routing Decisions** - Missing performance metrics:
   - No input/output token tracking in `RoutingDecision` table
   - No request-level latency (total time from route start to completion)
   - No model-level latency (time spent in LLM API call)
   - Metrics exist but aren't linked to individual routing decisions

### Requirements

1. **Strong Model Escalations Only** must contain:
   - Complete request trace including all components called
   - Cycle detection results (detected/not detected, hash distance)
   - Semantic cache results (hit/miss, confidence score, recommendation)
   - Judge results (complexity score, impact scope, reasoning, latency)
   - Original route decision and final route decision (if changed due to timeout)
   - Request preview (first 500 chars)

2. **All Routing Decisions** must contain:
   - Input tokens sent to model
   - Output tokens received from model
   - Total tokens (input + output)
   - Request latency (total end-to-end time)
   - Model latency (time spent in LLM API call)
   - Judge latency (if judge was invoked)

---

## Architecture Changes

### 1. Database Schema Extensions

#### Extended `RoutingDecision` Table

Add new columns to track tokens and latency:

```sql
ALTER TABLE routing_decisions ADD COLUMN input_tokens INTEGER DEFAULT 0;
ALTER TABLE routing_decisions ADD COLUMN output_tokens INTEGER DEFAULT 0;
ALTER TABLE routing_decisions ADD COLUMN total_tokens INTEGER DEFAULT 0;
ALTER TABLE routing_decisions ADD COLUMN request_latency_ms FLOAT DEFAULT 0.0;
ALTER TABLE routing_decisions ADD COLUMN model_latency_ms FLOAT DEFAULT 0.0;
ALTER TABLE routing_decisions ADD COLUMN judge_latency_ms FLOAT DEFAULT NULL;
```

**SQLAlchemy Model Update** (`sentinelrouter/sentinelrouter/models.py`):

```python
class RoutingDecision(Base):
    """
    Audit trail of every routing decision.
    """
    __tablename__ = "routing_decisions"

    decision_id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions.session_id"))
    request_id = Column(String, unique=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    model_used = Column(String)
    complexity_score = Column(Float)
    cost_incurred = Column(Float)
    prompt_hash = Column(String)
    impact_scope = Column(String, nullable=True)
    reason = Column(Text, nullable=True)
    
    # NEW: Token tracking
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    
    # NEW: Latency tracking
    request_latency_ms = Column(Float, default=0.0)  # Total end-to-end time
    model_latency_ms = Column(Float, default=0.0)    # Time in LLM API call
    judge_latency_ms = Column(Float, nullable=True)  # Judge invocation time (if used)

    # Relationships
    session = relationship("Session", back_populates="routing_decisions")
```

#### New `EscalationTrace` Table

Create dedicated table for strong model escalation traces:

```sql
CREATE TABLE escalation_traces (
    trace_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    request_id TEXT UNIQUE,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Request info
    request_preview TEXT,
    
    -- Cycle detection
    cycle_detected BOOLEAN DEFAULT 0,
    cycle_hash_distance INTEGER,
    cycle_repetition_count INTEGER,
    
    -- Semantic cache
    cache_hit BOOLEAN DEFAULT 0,
    cache_confidence FLOAT,
    cache_recommendation TEXT,  -- 'weak', 'strong', or NULL
    cache_weak_calls INTEGER DEFAULT 0,
    cache_strong_calls INTEGER DEFAULT 0,
    
    -- Judge
    judge_invoked BOOLEAN DEFAULT 0,
    judge_complexity_score FLOAT,
    judge_impact_scope TEXT,
    judge_reasoning TEXT,
    judge_latency_ms FLOAT,
    
    -- Routing decision
    initial_route_decision TEXT,  -- 'weak' or 'strong'
    final_route_decision TEXT,     -- May differ if timeout escalation
    escalation_reason TEXT,
    
    -- Model used
    model_used TEXT,
    
    FOREIGN KEY (session_id) REFERENCES sessions (session_id)
);
```

**SQLAlchemy Model** (`sentinelrouter/sentinelrouter/models.py`):

```python
class EscalationTrace(Base):
    """
    Detailed trace of strong model escalations showing full decision path.
    """
    __tablename__ = "escalation_traces"

    trace_id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions.session_id"))
    request_id = Column(String, unique=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Request info
    request_preview = Column(Text, nullable=True)
    
    # Cycle detection trace
    cycle_detected = Column(Boolean, default=False)
    cycle_hash_distance = Column(Integer, nullable=True)
    cycle_repetition_count = Column(Integer, nullable=True)
    
    # Semantic cache trace
    cache_hit = Column(Boolean, default=False)
    cache_confidence = Column(Float, nullable=True)
    cache_recommendation = Column(String, nullable=True)  # 'weak', 'strong', or NULL
    cache_weak_calls = Column(Integer, default=0)
    cache_strong_calls = Column(Integer, default=0)
    
    # Judge trace
    judge_invoked = Column(Boolean, default=False)
    judge_complexity_score = Column(Float, nullable=True)
    judge_impact_scope = Column(String, nullable=True)
    judge_reasoning = Column(Text, nullable=True)
    judge_latency_ms = Column(Float, nullable=True)
    
    # Routing decision trace
    initial_route_decision = Column(String)  # 'weak' or 'strong'
    final_route_decision = Column(String)    # May differ if timeout escalation
    escalation_reason = Column(Text, nullable=True)
    
    # Final model used
    model_used = Column(String)
    
    # Relationships
    session = relationship("Session", back_populates="escalation_traces")


# Update Session model to add relationship
class Session(Base):
    # ... existing fields ...
    
    # Add to relationships
    escalation_traces = relationship("EscalationTrace", back_populates="session")
```

---

## Implementation Plan

### Phase 1: Database Migration (1.5 hours)

**Step 1.1:** Create migration script

```python
# scripts/migrate_add_routing_metrics.py
"""
Migration script to add token and latency tracking to routing_decisions table
and create escalation_traces table.
"""
import sqlite3
from pathlib import Path

def migrate_database(db_path: str = "data/sentinelrouter.db"):
    """Add new columns and table for enhanced tracking."""
    db_path = Path(db_path)
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("Starting migration...")
    
    # Check if columns already exist
    cursor.execute("PRAGMA table_info(routing_decisions)")
    columns = [row[1] for row in cursor.fetchall()]
    
    # Add new columns to routing_decisions if they don't exist
    new_columns = [
        ("input_tokens", "INTEGER DEFAULT 0"),
        ("output_tokens", "INTEGER DEFAULT 0"),
        ("total_tokens", "INTEGER DEFAULT 0"),
        ("request_latency_ms", "REAL DEFAULT 0.0"),
        ("model_latency_ms", "REAL DEFAULT 0.0"),
        ("judge_latency_ms", "REAL"),
    ]
    
    for col_name, col_type in new_columns:
        if col_name not in columns:
            try:
                cursor.execute(f"ALTER TABLE routing_decisions ADD COLUMN {col_name} {col_type}")
                print(f"✅ Added column: routing_decisions.{col_name}")
            except sqlite3.OperationalError as e:
                print(f"⚠️  Column {col_name} might already exist: {e}")
    
    # Create escalation_traces table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS escalation_traces (
            trace_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            request_id TEXT UNIQUE,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            
            -- Request info
            request_preview TEXT,
            
            -- Cycle detection
            cycle_detected INTEGER DEFAULT 0,
            cycle_hash_distance INTEGER,
            cycle_repetition_count INTEGER,
            
            -- Semantic cache
            cache_hit INTEGER DEFAULT 0,
            cache_confidence REAL,
            cache_recommendation TEXT,
            cache_weak_calls INTEGER DEFAULT 0,
            cache_strong_calls INTEGER DEFAULT 0,
            
            -- Judge
            judge_invoked INTEGER DEFAULT 0,
            judge_complexity_score REAL,
            judge_impact_scope TEXT,
            judge_reasoning TEXT,
            judge_latency_ms REAL,
            
            -- Routing decision
            initial_route_decision TEXT,
            final_route_decision TEXT,
            escalation_reason TEXT,
            
            -- Model used
            model_used TEXT,
            
            FOREIGN KEY (session_id) REFERENCES sessions (session_id)
        )
    """)
    print("✅ Created escalation_traces table")
    
    # Create index on request_id for fast lookups
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_escalation_traces_request_id 
        ON escalation_traces(request_id)
    """)
    print("✅ Created index on escalation_traces.request_id")
    
    # Create index on session_id for session queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_escalation_traces_session_id 
        ON escalation_traces(session_id)
    """)
    print("✅ Created index on escalation_traces.session_id")
    
    conn.commit()
    conn.close()
    
    print("✅ Migration completed successfully")

if __name__ == "__main__":
    migrate_database()
```

**Step 1.2:** Update SQLAlchemy models (shown in Architecture section above)

**Step 1.3:** Test migration on dev database

```bash
cd /Users/shonhitwork/Documents/unstuckRouter
python scripts/migrate_add_routing_metrics.py
```

---

### Phase 2: Router Logic Enhancement (3 hours)

**Step 2.1:** Add trace context object to router

Create a trace context that accumulates information throughout the routing process:

```python
# sentinelrouter/sentinelrouter/trace_context.py
"""
Trace context for capturing routing decision flow.
"""
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

@dataclass
class TraceContext:
    """Accumulates trace information during routing process."""
    
    # Timing
    route_start_time: float = 0.0
    model_call_start_time: float = 0.0
    
    # Request info
    request_preview: str = ""
    
    # Cycle detection
    cycle_detected: bool = False
    cycle_hash_distance: Optional[int] = None
    cycle_repetition_count: Optional[int] = None
    
    # Semantic cache
    cache_hit: bool = False
    cache_confidence: float = 0.0
    cache_recommendation: Optional[str] = None
    cache_weak_calls: int = 0
    cache_strong_calls: int = 0
    
    # Judge
    judge_invoked: bool = False
    judge_complexity_score: Optional[float] = None
    judge_impact_scope: Optional[str] = None
    judge_reasoning: Optional[str] = None
    judge_latency_ms: Optional[float] = None
    
    # Routing decision
    initial_route_decision: str = "weak"
    final_route_decision: str = "weak"
    escalation_reason: str = ""
    
    # Token tracking
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    
    # Latency tracking
    request_latency_ms: float = 0.0
    model_latency_ms: float = 0.0
```

**Step 2.2:** Update `Router.route()` to populate trace context

Modify `sentinelrouter/sentinelrouter/router_logic.py`:

```python
async def route(
    self,
    session_id: str,
    prompt: str,
    messages: list,
    request_id: Optional[str] = None,
    client_ip: Optional[str] = None,
    use_judge: Optional[bool] = None,
    tier: Optional[str] = None,
) -> Dict[str, Any]:
    """Route a request to the appropriate model with full tracing."""
    
    # Create trace context
    from .trace_context import TraceContext
    trace = TraceContext()
    
    route_start = time.time()
    trace.route_start_time = route_start
    trace.request_preview = prompt[:500]  # First 500 chars
    
    # ... existing code ...
    
    # SEMANTIC CACHE: Capture cache trace
    cache_hit, cached_stats, cache_confidence = self.semantic_cache.check_cache(prompt, messages)
    trace.cache_hit = cache_hit
    trace.cache_confidence = cache_confidence
    
    if cache_hit and cached_stats:
        trace.cache_weak_calls = cached_stats.weak_calls
        trace.cache_strong_calls = cached_stats.strong_calls
        
        confident, confidence = self.semantic_cache.has_confident_history(prompt, messages)
        if confident:
            if cached_stats.weak_calls > cached_stats.strong_calls:
                trace.cache_recommendation = "weak"
            elif cached_stats.strong_calls > cached_stats.weak_calls:
                trace.cache_recommendation = "strong"
    
    # CYCLE DETECTION: Capture cycle trace
    cycle_detector = self._get_cycle_detector(session_id)
    cycle_detected = cycle_detector.detect_cycle_with_prompt(prompt)
    trace.cycle_detected = cycle_detected
    
    if cycle_detected:
        # Get cycle details from detector
        if hasattr(cycle_detector, 'successful_prompts'):
            # Count how many times this prompt appears
            current_hash = cycle_detector._hash_prompt(prompt)
            trace.cycle_repetition_count = sum(
                1 for ph in cycle_detector.successful_prompts if ph == current_hash
            )
        
        if hasattr(cycle_detector, 'recent_hashes') and cycle_detector.recent_hashes:
            trace.cycle_hash_distance = cycle_detector.recent_hashes[-1][0]
    
    # JUDGE: Capture judge trace
    if use_judge is True:
        trace.judge_invoked = True
        try:
            judge_start = time.time()
            complexity_score, impact_scope, reasoning = await self.judge.judge(prompt)
            judge_latency_ms = (time.time() - judge_start) * 1000
            
            trace.judge_complexity_score = complexity_score
            trace.judge_impact_scope = impact_scope
            trace.judge_reasoning = reasoning[:1000]  # Truncate to 1000 chars
            trace.judge_latency_ms = judge_latency_ms
        except Exception as e:
            logger.error(f"Judge failed: {e}")
            # Still record that judge was attempted
            trace.judge_reasoning = f"Judge failed: {str(e)}"
    
    # ROUTING DECISION: Capture initial decision
    route_decision = self._decide_route(
        complexity_score,
        impact_scope,
        threshold,
        strict_mode,
        cycle_detected,
    )
    trace.initial_route_decision = route_decision
    trace.final_route_decision = route_decision  # May change later
    
    # ... model calling logic ...
    
    # TRACK MODEL LATENCY
    trace.model_call_start_time = time.time()
    response = await client.chat_completion(messages)
    model_latency_ms = (time.time() - trace.model_call_start_time) * 1000
    trace.model_latency_ms = model_latency_ms
    
    # TRACK TOKENS
    if hasattr(response, 'usage') and response.usage:
        trace.input_tokens = response.usage.get('prompt_tokens', 0)
        trace.output_tokens = response.usage.get('completion_tokens', 0)
        trace.total_tokens = response.usage.get('total_tokens', 0)
    
    # CALCULATE TOTAL REQUEST LATENCY
    trace.request_latency_ms = (time.time() - route_start) * 1000
    
    # ... rest of existing code ...
    
    # Return trace context for logging
    return {
        "model_used": model_used,
        "response": response,
        "trace": trace,  # NEW
        # ... existing return fields ...
    }
```

**Step 2.3:** Handle timeout escalation trace updates

Update the timeout escalation section to track decision changes:

```python
if new_route_decision == "strong":
    # Update trace to show escalation
    trace.final_route_decision = "strong"
    trace.escalation_reason = "Weak model exceeded 15s timeout and judge recommended strong model"
    
    logger.info(f"Escalating to strong model due to timeout + judge recommendation")
    # ... rest of escalation logic ...
```

---

### Phase 3: Audit Logger Enhancement (2 hours)

**Step 3.1:** Update `log_routing_decision` to accept trace data

Modify `sentinelrouter/sentinelrouter/logging_audit.py`:

```python
class AuditLogger:
    """Records routing decisions and threshold adjustments to the database."""
    
    def log_routing_decision(
        self,
        session_id: str,
        request_id: str,
        model_used: str,
        complexity_score: float,
        cost_incurred: float,
        prompt_hash: str,
        impact_scope: Optional[str] = None,
        reason: Optional[str] = None,
        # NEW: Token and latency parameters
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        request_latency_ms: float = 0.0,
        model_latency_ms: float = 0.0,
        judge_latency_ms: Optional[float] = None,
    ) -> None:
        """
        Write a routing decision to the database with token and latency metrics.
        """
        decision = RoutingDecision(
            session_id=session_id,
            request_id=request_id,
            model_used=model_used,
            complexity_score=complexity_score,
            cost_incurred=cost_incurred,
            prompt_hash=prompt_hash,
            impact_scope=impact_scope,
            reason=reason,
            # NEW fields
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            request_latency_ms=request_latency_ms,
            model_latency_ms=model_latency_ms,
            judge_latency_ms=judge_latency_ms,
        )
        self.db.add(decision)
        self.db.commit()
        
        logging.debug(
            f"Logged routing decision for session {session_id}, model {model_used} | "
            f"Tokens: {input_tokens}/{output_tokens}, "
            f"Latency: request={request_latency_ms:.0f}ms, model={model_latency_ms:.0f}ms"
        )
```

**Step 3.2:** Add new method for escalation trace logging

```python
class AuditLogger:
    # ... existing methods ...
    
    def log_escalation_trace(
        self,
        session_id: str,
        request_id: str,
        trace_data: dict,
    ) -> None:
        """
        Log detailed escalation trace for strong model usage.
        
        Args:
            session_id: Session identifier
            request_id: Request identifier
            trace_data: Dictionary containing all trace fields
        """
        from .models import EscalationTrace
        
        trace = EscalationTrace(
            session_id=session_id,
            request_id=request_id,
            request_preview=trace_data.get('request_preview'),
            cycle_detected=trace_data.get('cycle_detected', False),
            cycle_hash_distance=trace_data.get('cycle_hash_distance'),
            cycle_repetition_count=trace_data.get('cycle_repetition_count'),
            cache_hit=trace_data.get('cache_hit', False),
            cache_confidence=trace_data.get('cache_confidence'),
            cache_recommendation=trace_data.get('cache_recommendation'),
            cache_weak_calls=trace_data.get('cache_weak_calls', 0),
            cache_strong_calls=trace_data.get('cache_strong_calls', 0),
            judge_invoked=trace_data.get('judge_invoked', False),
            judge_complexity_score=trace_data.get('judge_complexity_score'),
            judge_impact_scope=trace_data.get('judge_impact_scope'),
            judge_reasoning=trace_data.get('judge_reasoning'),
            judge_latency_ms=trace_data.get('judge_latency_ms'),
            initial_route_decision=trace_data.get('initial_route_decision'),
            final_route_decision=trace_data.get('final_route_decision'),
            escalation_reason=trace_data.get('escalation_reason'),
            model_used=trace_data.get('model_used'),
        )
        
        self.db.add(trace)
        self.db.commit()
        
        logging.debug(
            f"Logged escalation trace for session {session_id}, request {request_id} | "
            f"Initial: {trace_data.get('initial_route_decision')} -> "
            f"Final: {trace_data.get('final_route_decision')}"
        )
```

**Step 3.3:** Update `LoggingAudit` facade class

```python
class LoggingAudit:
    """Unified logging and audit facade."""
    
    def log_routing_decision(
        self,
        session_id: str,
        request_id: str,
        model_used: str,
        complexity_score: float,
        cost_incurred: float,
        prompt_hash: str = "",
        impact_scope: Optional[str] = None,
        reason: Optional[str] = None,
        # NEW parameters
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        request_latency_ms: float = 0.0,
        model_latency_ms: float = 0.0,
        judge_latency_ms: Optional[float] = None,
    ) -> None:
        """Delegate to AuditLogger with new parameters."""
        self.audit_logger.log_routing_decision(
            session_id=session_id,
            request_id=request_id,
            model_used=model_used,
            complexity_score=complexity_score,
            cost_incurred=cost_incurred,
            prompt_hash=prompt_hash,
            impact_scope=impact_scope,
            reason=reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            request_latency_ms=request_latency_ms,
            model_latency_ms=model_latency_ms,
            judge_latency_ms=judge_latency_ms,
        )
    
    async def log_escalation_trace(
        self,
        session_id: str,
        request_id: str,
        trace_data: dict,
    ) -> None:
        """Log escalation trace asynchronously."""
        await asyncio.to_thread(
            self.audit_logger.log_escalation_trace,
            session_id=session_id,
            request_id=request_id,
            trace_data=trace_data,
        )
```

---

### Phase 4: Router Integration (1.5 hours)

**Step 4.1:** Update router to call enhanced logging

Modify the logging section in `router_logic.py`:

```python
# 8. Record decision in audit log with trace data
await self.audit.log_routing_decision(
    session_id=session_id,
    request_id=request_id,
    model_used=model_used,
    complexity_score=complexity_score,
    cost_incurred=response.cost,
    prompt_hash=str(prompt_hash_int),
    impact_scope=impact_scope,
    reason=decision_reason,
    # NEW: Add trace data
    input_tokens=trace.input_tokens,
    output_tokens=trace.output_tokens,
    total_tokens=trace.total_tokens,
    request_latency_ms=trace.request_latency_ms,
    model_latency_ms=trace.model_latency_ms,
    judge_latency_ms=trace.judge_latency_ms,
)

# 8b. If strong model was used, log escalation trace
if route_decision == "strong" or trace.final_route_decision == "strong":
    trace_data = {
        'request_preview': trace.request_preview,
        'cycle_detected': trace.cycle_detected,
        'cycle_hash_distance': trace.cycle_hash_distance,
        'cycle_repetition_count': trace.cycle_repetition_count,
        'cache_hit': trace.cache_hit,
        'cache_confidence': trace.cache_confidence,
        'cache_recommendation': trace.cache_recommendation,
        'cache_weak_calls': trace.cache_weak_calls,
        'cache_strong_calls': trace.cache_strong_calls,
        'judge_invoked': trace.judge_invoked,
        'judge_complexity_score': trace.judge_complexity_score,
        'judge_impact_scope': trace.judge_impact_scope,
        'judge_reasoning': trace.judge_reasoning,
        'judge_latency_ms': trace.judge_latency_ms,
        'initial_route_decision': trace.initial_route_decision,
        'final_route_decision': trace.final_route_decision,
        'escalation_reason': trace.escalation_reason,
        'model_used': model_used,
    }
    await self.audit.log_escalation_trace(
        session_id=session_id,
        request_id=request_id,
        trace_data=trace_data,
    )
    logger.info(f"Logged escalation trace for strong model usage: {model_used}")
```

---

### Phase 5: Dashboard Enhancement (2 hours)

**Step 5.1:** Add API endpoint for escalation traces

Add to `sentinelrouter/sentinelrouter/dashboard.py`:

```python
@dashboard_app.get("/api/dashboard/escalation-traces")
async def get_escalation_traces(
    db: Session = Depends(get_dbsession),
    limit: int = 50,
    session_id: Optional[str] = None
):
    """Get recent escalation traces with full decision path."""
    from .models import EscalationTrace
    
    query = db.query(EscalationTrace).order_by(EscalationTrace.timestamp.desc())
    
    if session_id:
        query = query.filter(EscalationTrace.session_id == session_id)
    
    traces = query.limit(limit).all()
    
    return {
        "traces": [
            {
                "trace_id": t.trace_id,
                "session_id": t.session_id,
                "request_id": t.request_id,
                "timestamp": t.timestamp.isoformat() if t.timestamp else None,
                "request_preview": t.request_preview,
                "cycle_detected": t.cycle_detected,
                "cycle_hash_distance": t.cycle_hash_distance,
                "cycle_repetition_count": t.cycle_repetition_count,
                "cache_hit": t.cache_hit,
                "cache_confidence": t.cache_confidence,
                "cache_recommendation": t.cache_recommendation,
                "cache_weak_calls": t.cache_weak_calls,
                "cache_strong_calls": t.cache_strong_calls,
                "judge_invoked": t.judge_invoked,
                "judge_complexity_score": t.judge_complexity_score,
                "judge_impact_scope": t.judge_impact_scope,
                "judge_reasoning": t.judge_reasoning,
                "judge_latency_ms": t.judge_latency_ms,
                "initial_route_decision": t.initial_route_decision,
                "final_route_decision": t.final_route_decision,
                "escalation_reason": t.escalation_reason,
                "model_used": t.model_used,
            }
            for t in traces
        ],
        "total": len(traces)
    }
```

**Step 5.2:** Update logs endpoint to include token/latency data

Modify existing endpoint:

```python
@dashboard_app.get("/api/dashboard/logs")
async def get_routing_logs(
    db: Session = Depends(get_dbsession), 
    limit: int = 50,
    include_preview: bool = False
):
    """Get recent routing decision logs with token and latency metrics."""
    logs = db.query(RoutingDecision)\
             .order_by(RoutingDecision.timestamp.desc())\
             .limit(limit).all()
    
    result = []
    for log in logs:
        log_entry = {
            "session_id": log.session_id,
            "request_id": log.request_id,
            "model_used": log.model_used,
            "complexity_score": log.complexity_score or 0.0,
            "cost_incurred": log.cost_incurred or 0.0,
            "impact_scope": log.impact_scope or "UNKNOWN",
            "reason": log.reason or "",
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            # NEW: Token and latency data
            "input_tokens": log.input_tokens or 0,
            "output_tokens": log.output_tokens or 0,
            "total_tokens": log.total_tokens or 0,
            "request_latency_ms": log.request_latency_ms or 0.0,
            "model_latency_ms": log.model_latency_ms or 0.0,
            "judge_latency_ms": log.judge_latency_ms,
        }
        result.append(log_entry)
    
    return {"logs": result, "count": len(result)}
```

**Step 5.3:** Update dashboard UI to display new data

Enhance the "Router Logic" tab in the dashboard HTML to show tokens and latency:

```javascript
// In dashboard.py, update the JavaScript for rendering logs
function renderLog(log, index) {
    const isEscalation = log.model_used && (
        log.model_used.includes('opus') || 
        log.model_used.includes('claude')
    );
    
    return `
        <div class="log-entry ${isEscalation ? 'escalation' : ''}">
            <div class="log-header">
                <span class="log-model">${log.model_used}</span>
                <span>${log.timestamp}</span>
                ${isEscalation ? '<span class="badge-escalation">ESCALATION</span>' : ''}
            </div>
            <div class="log-reason">
                <strong>Decision:</strong> ${log.reason}
            </div>
            <div class="log-details">
                <div class="log-detail-item">Complexity: ${log.complexity_score.toFixed(2)}</div>
                <div class="log-detail-item">Impact: ${log.impact_scope}</div>
                <div class="log-detail-item">Cost: $${log.cost_incurred.toFixed(4)}</div>
            </div>
            <div class="log-details">
                <div class="log-detail-item">Tokens: ${log.input_tokens}/${log.output_tokens} (${log.total_tokens})</div>
                <div class="log-detail-item">Request: ${log.request_latency_ms.toFixed(0)}ms</div>
                <div class="log-detail-item">Model: ${log.model_latency_ms.toFixed(0)}ms</div>
                ${log.judge_latency_ms ? `<div class="log-detail-item">Judge: ${log.judge_latency_ms.toFixed(0)}ms</div>` : ''}
            </div>
            ${isEscalation ? `
                <div class="log-trace">
                    <button onclick="loadEscalationTrace('${log.request_id}')">
                        🔍 View Full Trace
                    </button>
                </div>
            ` : ''}
        </div>
    `;
}
```

---

## Testing Plan

### Unit Tests

**Test 1:** Database schema migration

```python
# tests/test_migration_routing_metrics.py
import pytest
import sqlite3
from pathlib import Path
from scripts.migrate_add_routing_metrics import migrate_database

def test_migration_adds_columns():
    """Test that migration adds required columns to routing_decisions."""
    test_db = "test_migration.db"
    
    # Create minimal database
    conn = sqlite3.connect(test_db)
    conn.execute("""
        CREATE TABLE routing_decisions (
            decision_id INTEGER PRIMARY KEY,
            session_id TEXT,
            model_used TEXT
        )
    """)
    conn.commit()
    conn.close()
    
    # Run migration
    migrate_database(test_db)
    
    # Verify columns exist
    conn = sqlite3.connect(test_db)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(routing_decisions)")
    columns = {row[1] for row in cursor.fetchall()}
    conn.close()
    
    expected_columns = {
        'input_tokens', 'output_tokens', 'total_tokens',
        'request_latency_ms', 'model_latency_ms', 'judge_latency_ms'
    }
    
    assert expected_columns.issubset(columns), "Missing expected columns"
    
    # Cleanup
    Path(test_db).unlink()

def test_migration_creates_escalation_traces():
    """Test that migration creates escalation_traces table."""
    test_db = "test_escalation.db"
    
    # Create minimal database
    conn = sqlite3.connect(test_db)
    conn.execute("CREATE TABLE sessions (session_id TEXT PRIMARY KEY)")
    conn.commit()
    conn.close()
    
    # Run migration
    migrate_database(test_db)
    
    # Verify table exists
    conn = sqlite3.connect(test_db)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='escalation_traces'")
    result = cursor.fetchone()
    conn.close()
    
    assert result is not None, "escalation_traces table not created"
    
    # Cleanup
    Path(test_db).unlink()
```

**Test 2:** Trace context population

```python
# tests/test_trace_context.py
import pytest
from sentinelrouter.sentinelrouter.trace_context import TraceContext

def test_trace_context_initialization():
    """Test TraceContext initializes with defaults."""
    trace = TraceContext()
    
    assert trace.cycle_detected is False
    assert trace.cache_hit is False
    assert trace.judge_invoked is False
    assert trace.input_tokens == 0
    assert trace.request_latency_ms == 0.0

def test_trace_context_population():
    """Test TraceContext can be populated with data."""
    trace = TraceContext()
    
    trace.cycle_detected = True
    trace.cycle_repetition_count = 4
    trace.cache_hit = True
    trace.cache_confidence = 0.95
    trace.input_tokens = 1500
    trace.output_tokens = 800
    
    assert trace.cycle_detected is True
    assert trace.cycle_repetition_count == 4
    assert trace.cache_confidence == 0.95
    assert trace.input_tokens == 1500
```

**Test 3:** Enhanced audit logging

```python
# tests/test_audit_logging_enhanced.py
import pytest
from sentinelrouter.sentinelrouter.logging_audit import AuditLogger
from sentinelrouter.sentinelrouter.database import SessionLocal
from sentinelrouter.sentinelrouter.models import RoutingDecision, EscalationTrace

def test_log_routing_decision_with_metrics():
    """Test logging routing decision with token and latency metrics."""
    db = SessionLocal()
    audit = AuditLogger(db)
    
    audit.log_routing_decision(
        session_id="test_session",
        request_id="test_request_1",
        model_used="deepseek-chat",
        complexity_score=0.45,
        cost_incurred=0.002,
        prompt_hash="abc123",
        impact_scope="LOW",
        reason="Below threshold",
        input_tokens=1200,
        output_tokens=650,
        total_tokens=1850,
        request_latency_ms=2500.0,
        model_latency_ms=2100.0,
        judge_latency_ms=350.0,
    )
    
    # Verify in database
    decision = db.query(RoutingDecision).filter(
        RoutingDecision.request_id == "test_request_1"
    ).first()
    
    assert decision is not None
    assert decision.input_tokens == 1200
    assert decision.output_tokens == 650
    assert decision.total_tokens == 1850
    assert decision.request_latency_ms == 2500.0
    assert decision.model_latency_ms == 2100.0
    assert decision.judge_latency_ms == 350.0
    
    db.close()

def test_log_escalation_trace():
    """Test logging escalation trace."""
    db = SessionLocal()
    audit = AuditLogger(db)
    
    trace_data = {
        'request_preview': 'Test prompt...',
        'cycle_detected': True,
        'cycle_repetition_count': 4,
        'cache_hit': True,
        'cache_confidence': 0.92,
        'cache_recommendation': 'strong',
        'judge_invoked': True,
        'judge_complexity_score': 0.85,
        'judge_impact_scope': 'HIGH',
        'initial_route_decision': 'weak',
        'final_route_decision': 'strong',
        'escalation_reason': 'Cycle detected',
        'model_used': 'claude-3-opus-20240229',
    }
    
    audit.log_escalation_trace(
        session_id="test_session",
        request_id="test_escalation_1",
        trace_data=trace_data,
    )
    
    # Verify in database
    trace = db.query(EscalationTrace).filter(
        EscalationTrace.request_id == "test_escalation_1"
    ).first()
    
    assert trace is not None
    assert trace.cycle_detected is True
    assert trace.cycle_repetition_count == 4
    assert trace.cache_confidence == 0.92
    assert trace.judge_complexity_score == 0.85
    assert trace.final_route_decision == "strong"
    
    db.close()
```

### Integration Tests

```python
# tests/test_routing_with_tracing.py
import pytest
import asyncio
from sentinelrouter.sentinelrouter.router_logic import Router
from sentinelrouter.sentinelrouter.database import SessionLocal
from sentinelrouter.sentinelrouter.models import RoutingDecision, EscalationTrace

@pytest.mark.asyncio
async def test_route_captures_trace_data():
    """Test that routing captures full trace data."""
    router = Router()
    
    result = await router.route(
        session_id="test_trace_session",
        prompt="Explain quantum computing in detail",
        messages=[{"role": "user", "content": "Explain quantum computing in detail"}],
        request_id="trace_test_1",
        use_judge=True,
    )
    
    # Verify trace in response
    assert "trace" in result
    trace = result["trace"]
    assert trace.request_latency_ms > 0
    assert trace.model_latency_ms > 0
    assert trace.input_tokens > 0
    assert trace.output_tokens > 0
    
    # Verify in database
    db = SessionLocal()
    decision = db.query(RoutingDecision).filter(
        RoutingDecision.request_id == "trace_test_1"
    ).first()
    
    assert decision is not None
    assert decision.input_tokens == trace.input_tokens
    assert decision.request_latency_ms == trace.request_latency_ms
    
    db.close()

@pytest.mark.asyncio
async def test_strong_model_creates_escalation_trace():
    """Test that strong model usage creates escalation trace."""
    router = Router()
    
    # Force strong model by using high complexity prompt
    result = await router.route(
        session_id="test_escalation_session",
        prompt="Design a production-ready microservices architecture for e-commerce",
        messages=[{"role": "user", "content": "Design a production-ready microservices architecture"}],
        request_id="escalation_trace_test_1",
        use_judge=True,
    )
    
    # If strong model was used, check for escalation trace
    if result["tier"] == "strong":
        db = SessionLocal()
        trace = db.query(EscalationTrace).filter(
            EscalationTrace.request_id == "escalation_trace_test_1"
        ).first()
        
        assert trace is not None
        assert trace.judge_invoked is True
        assert trace.model_used == result["model_used"]
        
        db.close()
```

---

## Acceptance Criteria

### ✅ Strong Model Escalations

- [ ] `escalation_traces` table exists with all required columns
- [ ] Every strong model usage creates an escalation trace entry
- [ ] Escalation trace contains:
  - [ ] Request preview (first 500 chars)
  - [ ] Cycle detection status and details
  - [ ] Semantic cache hit/miss, confidence, and recommendation
  - [ ] Judge results (if invoked)
  - [ ] Initial and final routing decisions
  - [ ] Escalation reason (if decision changed)
- [ ] Dashboard displays escalation traces with "View Full Trace" button
- [ ] Clicking "View Full Trace" shows complete decision path

### ✅ All Routing Decisions

- [ ] `routing_decisions` table has new columns for tokens and latency
- [ ] Every routing decision records:
  - [ ] Input tokens, output tokens, total tokens
  - [ ] Request latency (end-to-end time)
  - [ ] Model latency (LLM API call time)
  - [ ] Judge latency (if judge was invoked)
- [ ] Dashboard logs tab displays token and latency metrics
- [ ] API endpoint returns token/latency data for all decisions

### ✅ Testing

- [ ] All unit tests pass
- [ ] Integration tests verify trace data is captured correctly
- [ ] Manual testing confirms dashboard displays new data
- [ ] Migration script runs successfully on production database

---

## Rollback Plan

If issues arise during deployment:

1. **Database Rollback:**
   ```sql
   -- Remove new columns from routing_decisions
   ALTER TABLE routing_decisions DROP COLUMN input_tokens;
   ALTER TABLE routing_decisions DROP COLUMN output_tokens;
   ALTER TABLE routing_decisions DROP COLUMN total_tokens;
   ALTER TABLE routing_decisions DROP COLUMN request_latency_ms;
   ALTER TABLE routing_decisions DROP COLUMN model_latency_ms;
   ALTER TABLE routing_decisions DROP COLUMN judge_latency_ms;
   
   -- Drop escalation_traces table
   DROP TABLE escalation_traces;
   ```

2. **Code Rollback:**
   - Revert `router_logic.py` changes
   - Revert `logging_audit.py` changes
   - Revert `dashboard.py` API endpoints
   - Remove `trace_context.py` file

3. **Restart Services:**
   ```bash
   docker-compose restart sentinelrouter
   ```

---

## Timeline

| Phase | Task | Time | Status |
|-------|------|------|--------|
| 1 | Database migration script | 0.5h | ⏳ Not Started |
| 1 | Update SQLAlchemy models | 0.5h | ⏳ Not Started |
| 1 | Test migration | 0.5h | ⏳ Not Started |
| 2 | Create TraceContext class | 0.5h | ⏳ Not Started |
| 2 | Update Router.route() | 1.5h | ⏳ Not Started |
| 2 | Handle timeout escalation | 1h | ⏳ Not Started |
| 3 | Update log_routing_decision | 0.5h | ⏳ Not Started |
| 3 | Add log_escalation_trace | 1h | ⏳ Not Started |
| 3 | Update LoggingAudit facade | 0.5h | ⏳ Not Started |
| 4 | Integrate enhanced logging | 1h | ⏳ Not Started |
| 4 | Test router integration | 0.5h | ⏳ Not Started |
| 5 | Add escalation traces API | 0.5h | ⏳ Not Started |
| 5 | Update logs API | 0.5h | ⏳ Not Started |
| 5 | Enhance dashboard UI | 1h | ⏳ Not Started |
| **Total** | | **10h** | |

---

## Success Metrics

After implementation, the system should provide:

1. **Complete Visibility:** Every strong model escalation shows full decision trace
2. **Performance Insights:** Token and latency metrics for every request
3. **Debugging Capability:** Ability to trace why any request was routed to strong model
4. **Historical Analysis:** Query escalation patterns over time
5. **Dashboard Clarity:** Clear display of metrics in UI for real-time monitoring

---

## Related Issues

- Dashboard latency enhancement (#issues_requestLatencyDashboard.md)
- Cycle detection improvements (completed Dec 14, 2025)
- Semantic cache confidence tracking (in production)

---

## Notes

- **Performance Impact:** Additional database writes for escalation traces (~10-20% of total requests assuming 10-20% escalation rate)
- **Storage:** Escalation traces table will grow over time; consider retention policy
- **Privacy:** Request preview truncated to 500 chars to limit sensitive data exposure
- **Backward Compatibility:** New columns have default values; existing code continues to work

