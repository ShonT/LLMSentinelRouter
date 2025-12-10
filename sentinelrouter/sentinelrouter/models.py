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
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Session(Base):
    """
    Represents a client session with a budget limit.
    """
    __tablename__ = "sessions"

    session_id = Column(String, primary_key=True)
    client_ip = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    max_cost_per_session = Column(Float, default=10.0)
    current_cost = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)

    # Relationships
    routing_decisions = relationship("RoutingDecision", back_populates="session")
    cycle_nodes = relationship("CycleNode", back_populates="session")
    escalation_logs = relationship("EscalationLog", back_populates="session")


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