"""
SQLAlchemy ORM models for SentinelRouter database.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    Index,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Session(Base):
    """
    Represents a client session with a budget limit and tier.

    Tier determines rate limits:
    - 'free': Lower rate limits (default)
    - 'paid': Higher rate limits
    - 'premium': Highest rate limits

    Uses version column for optimistic concurrency control to prevent
    race conditions during budget updates.
    """

    __tablename__ = "sessions"

    session_id = Column(String, primary_key=True)
    client_ip = Column(String, nullable=True)
    tier = Column(String, default="free", nullable=False)  # 'free', 'paid', 'premium'
    created_at = Column(DateTime, default=datetime.utcnow)
    max_cost_per_session = Column(Float, default=10.0)
    current_cost = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    version = Column(
        Integer, default=0, nullable=False
    )  # For optimistic concurrency control

    # Relationships
    routing_decisions = relationship("RoutingDecision", back_populates="session")
    cycle_nodes = relationship("CycleNode", back_populates="session")
    escalation_logs = relationship("EscalationLog", back_populates="session")
    escalation_traces = relationship("EscalationTrace", back_populates="session")


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
    cost_incurred = Column(Float)  # Final cost used (canonical)
    cost_source = Column(
        String, default="unknown"
    )  # "provider" | "computed" | "unknown"
    computed_cost = Column(Float, nullable=True)  # Computed fallback for audit/debug
    prompt_hash = Column(String)
    impact_scope = Column(String, nullable=True)
    reason = Column(Text, nullable=True)

    # NEW: Token tracking
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)

    # NEW: Latency tracking
    request_latency_ms = Column(Float, default=0.0)  # Total end-to-end time
    model_latency_ms = Column(Float, default=0.0)  # Time in LLM API call
    judge_latency_ms = Column(Float, nullable=True)  # Judge invocation time (if used)

    # Relationships
    session = relationship("Session", back_populates="routing_decisions")


class CycleNode(Base):
    """
    Semantic hashes for cycle detection.
    """

    __tablename__ = "cycle_detection"

    hash_id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions.session_id"))
    prompt_hash = Column(String)
    response_hash = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

    # Relationships
    session = relationship("Session", back_populates="cycle_nodes")


class EscalationLog(Base):
    """
    Log of threshold adjustments.
    """

    __tablename__ = "escalation_log"

    log_id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions.session_id"))
    escalation_rate = Column(Float)
    threshold_before = Column(Float)
    threshold_after = Column(Float)
    changed_at = Column(DateTime, default=datetime.utcnow)
    reason = Column(Text, nullable=True)

    # Relationships
    session = relationship("Session", back_populates="escalation_logs")


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
    cycle_hash_distance = Column(Float, nullable=True)
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
    final_route_decision = Column(String)  # May differ if timeout escalation
    escalation_reason = Column(Text, nullable=True)

    # Final model used
    model_used = Column(String)

    # Relationships
    session = relationship("Session", back_populates="escalation_traces")


class SemanticCacheEntry(Base):
    """
    Stores individual request/response observations keyed by semantic hash.
    """

    __tablename__ = "semantic_cache_entries"

    entry_id = Column(Integer, primary_key=True, autoincrement=True)
    semantic_hash = Column(String, index=True)
    context_hash = Column(String, index=True, nullable=True)
    prompt_preview = Column(Text, nullable=True)
    response_preview = Column(Text, nullable=True)
    latency_ms = Column(Float, default=0.0)
    judge_invoked = Column(Boolean, default=True)
    judge_latency_ms = Column(Float, nullable=True)
    model_used = Column(String)
    complexity_score = Column(Float, nullable=True)
    impact_scope = Column(String, nullable=True)
    cost = Column(Float, default=0.0)
    total_tokens = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class SemanticCacheStats(Base):
    """
    Aggregated statistics per semantic hash for fast confidence calculations.
    """

    __tablename__ = "semantic_cache_stats"

    semantic_hash = Column(String, primary_key=True)
    total_calls = Column(Integer, default=0)
    weak_calls = Column(Integer, default=0)
    strong_calls = Column(Integer, default=0)
    judge_invocations = Column(Integer, default=0)
    total_latency_ms = Column(Float, default=0.0)
    total_latency_ms_sq = Column(Float, default=0.0)
    total_cost = Column(Float, default=0.0)
    total_tokens = Column(Integer, default=0)
    last_model = Column(String, nullable=True)
    last_called_at = Column(DateTime, default=datetime.utcnow)
    first_seen_at = Column(DateTime, default=datetime.utcnow)


# Helpful indexes for faster lookups
Index("ix_semantic_cache_stats_last_called", SemanticCacheStats.last_called_at)
Index(
    "ix_semantic_cache_entries_semantic_hash_created",
    SemanticCacheEntry.semantic_hash,
    SemanticCacheEntry.created_at,
)
