"""
Admin Policy Configuration Schema.

Defines the safe, explicit set of admin-editable policy fields.
These are runtime-tunable knobs that affect future routing decisions
without modifying topology or credentials.
"""

from pydantic import BaseModel, Field
from typing import Literal, Optional


class BudgetControl(BaseModel):
    """Budget and escalation policy controls."""
    max_cost_per_session: float = Field(
        default=25.0,
        ge=0.0,
        description="Maximum cost per session before budget kill-switch triggers (USD)."
    )
    escalation_rate_limit: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description="Target escalation rate for dynamic threshold adjustment (0.0-1.0)."
    )
    rolling_window_size: int = Field(
        default=20,
        ge=1,
        description="Number of recent decisions considered for escalation rate calculation."
    )


class JudgePolicy(BaseModel):
    """Judge system policy controls."""
    enabled: bool = Field(
        default=False,
        description="Whether the judge system is active."
    )
    mode: Literal["always", "never", "smart"] = Field(
        default="smart",
        description="Judge invocation mode: always, never, or smart (automatic)."
    )
    complexity_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Threshold for classifying queries as complex (0.0-1.0)."
    )


class SemanticCachePolicy(BaseModel):
    """Semantic cache policy controls."""
    enabled: bool = Field(
        default=False,
        description="Whether semantic caching is active."
    )
    min_samples: int = Field(
        default=3,
        ge=1,
        description="Minimum samples needed before cache entry is considered reliable."
    )
    confidence_threshold: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="Confidence threshold for using cached routing decision (0.0-1.0)."
    )
    ttl_seconds: int = Field(
        default=604800,  # 7 days
        ge=0,
        description="Time-to-live for cache entries in seconds."
    )


class CycleDetectionPolicy(BaseModel):
    """Cycle detection policy controls."""
    enabled: bool = Field(
        default=True,
        description="Whether cycle detection is active."
    )
    window_size: int = Field(
        default=100,
        ge=1,
        description="Number of recent requests to consider for cycle detection."
    )
    simhash_distance_threshold: int = Field(
        default=3,
        ge=0,
        description="Hamming distance threshold for SimHash-based similarity detection."
    )


class AdminPolicyConfig(BaseModel):
    """
    Complete admin-editable policy configuration.
    
    This defines the ONLY fields that can be modified at runtime via Admin UI.
    All structural config (keys, models, routing topology) remains file-based.
    """
    budget_control: BudgetControl = Field(
        default_factory=BudgetControl,
        description="Budget and escalation rate controls."
    )
    judge: JudgePolicy = Field(
        default_factory=JudgePolicy,
        description="Judge system policy."
    )
    semantic_cache: SemanticCachePolicy = Field(
        default_factory=SemanticCachePolicy,
        description="Semantic cache policy."
    )
    cycle_detection: CycleDetectionPolicy = Field(
        default_factory=CycleDetectionPolicy,
        description="Cycle detection policy."
    )


class AdminPolicyUpdate(BaseModel):
    """
    Partial update model for admin policy.
    All fields are optional to allow selective updates.
    """
    budget_control: Optional[BudgetControl] = None
    judge: Optional[JudgePolicy] = None
    semantic_cache: Optional[SemanticCachePolicy] = None
    cycle_detection: Optional[CycleDetectionPolicy] = None


class AdminStateResponse(BaseModel):
    """Read-only state information for operators."""
    
    class RoutingState(BaseModel):
        """Current routing configuration and state."""
        weak_models: list[str] = Field(default_factory=list)
        strong_models: list[str] = Field(default_factory=list)
        routing_order: list[str] = Field(default_factory=list)
        weak_strong_ratio: Optional[float] = None
        
    class JudgeState(BaseModel):
        """Judge system effectiveness."""
        invoked_count: int = 0
        skipped_count: int = 0
        skip_rate: float = 0.0
        success_rate: float = 0.0
        avg_latency_ms: float = 0.0
        
    class SemanticCacheState(BaseModel):
        """Semantic cache effectiveness."""
        hit_count: int = 0
        miss_count: int = 0
        hit_rate: float = 0.0
        active_clusters: int = 0
        judge_skip_attribution: float = 0.0  # % of judge skips due to cache
        
    class EscalationState(BaseModel):
        """Current escalation behavior."""
        current_rate: float = 0.0
        target_rate: float = 0.05
        is_strict_mode: bool = False
        effective_threshold: float = 0.5
        
    routing: RoutingState = Field(default_factory=RoutingState)
    judge: JudgeState = Field(default_factory=JudgeState)
    semantic_cache: SemanticCacheState = Field(default_factory=SemanticCacheState)
    escalation: EscalationState = Field(default_factory=EscalationState)
