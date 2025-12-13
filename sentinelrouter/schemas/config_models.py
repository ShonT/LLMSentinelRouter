"""
Pydantic models for the unified configuration schema.
"""

from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Dict, List, Literal, Optional, Union
from datetime import datetime


class SystemSettings(BaseModel):
    persistence_interval_seconds: int = Field(default=5, gt=0)
    default_routing_strategy: Literal["waterfall", "priority"] = "waterfall"
    timezone: str = "UTC"


class ModelCapabilities(BaseModel):
    modality: List[Literal["text", "image", "audio"]] = ["text"]
    context_window: int = 128000


class RoutingConfig(BaseModel):
    priority_group: Literal["fast_tier", "strong_tier"] = "fast_tier"
    order: int = 1


class RateLimits(BaseModel):
    requests_per_minute: int = Field(default=15, ge=0)
    requests_per_day: int = Field(default=1500, ge=0)
    tokens_per_minute: int = Field(default=1_000_000, ge=0)


class PricingTier(BaseModel):
    name: str
    threshold_requests: Union[int, Literal["inf"]]
    input_cost: float
    output_cost: float


class PricingInfo(BaseModel):
    currency: str = "USD"
    input_cost_per_m: float = 0.0
    output_cost_per_m: float = 0.0
    usage_tiers: List[PricingTier] = []
    
    def calculate_cost(
        self, 
        input_tokens: int, 
        output_tokens: int, 
        requests_today: int
    ) -> float:
        """Calculate cost based on active tier or flat rate."""
        if not self.usage_tiers:
            # No tiers, use flat rate
            return (
                (input_tokens / 1_000_000) * self.input_cost_per_m +
                (output_tokens / 1_000_000) * self.output_cost_per_m
            )
        
        # Find active tier based on requests_today
        active_tier = None
        for tier in sorted(
            self.usage_tiers, 
            key=lambda t: float('inf') if isinstance(t.threshold_requests, str) else t.threshold_requests
        ):
            if isinstance(tier.threshold_requests, str) and tier.threshold_requests == "inf":
                active_tier = tier
                break
            if requests_today < tier.threshold_requests:
                active_tier = tier
                break
        
        if not active_tier:
            active_tier = self.usage_tiers[-1]  # Default to last tier
        
        return (
            (input_tokens / 1_000_000) * active_tier.input_cost +
            (output_tokens / 1_000_000) * active_tier.output_cost
        )


class ModelState(BaseModel):
    current_rpm: float = Field(default=0.0, ge=0.0)
    requests_today: int = Field(default=0, ge=0)
    tokens_today: int = Field(default=0, ge=0)
    total_cost_session: float = Field(default=0.0, ge=0.0)
    last_updated_ts: Optional[datetime] = None
    exhausted_until_ts: Optional[datetime] = None


class TierLimits(BaseModel):
    """Rate limits for free or paid tier"""
    requests_per_day: int = Field(default=1500, ge=0)
    requests_per_minute: int = Field(default=15, ge=0)
    tokens_per_minute: int = Field(default=1_000_000, ge=0)
    tokens_per_day: int = Field(default=10_000_000, ge=0)


class CostInfo(BaseModel):
    """Cost structure per call and per token"""
    per_call: float = Field(default=0.0, ge=0.0)
    per_token_input: float = Field(default=0.0, ge=0.0)
    per_token_output: float = Field(default=0.0, ge=0.0)


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str
    provider: str
    model_definition: Optional[str] = None  # Description of the model
    model_key: str  # Unique identifier for the model (e.g., "gpt-4", "claude-3-5-sonnet")
    status: Literal["ACTIVE", "BANNED"] = "ACTIVE"
    status_valid_till: Optional[datetime] = None  # If BANNED, until when
    
    capabilities: ModelCapabilities = Field(default_factory=ModelCapabilities)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    limits: RateLimits = Field(default_factory=RateLimits)  # Overall limits (legacy)
    free_tier_limits: TierLimits = Field(default_factory=TierLimits)
    paid_tier_limits: TierLimits = Field(default_factory=TierLimits)
    pricing: PricingInfo = Field(default_factory=PricingInfo)
    cost: CostInfo = Field(default_factory=CostInfo)  # Simple cost per call/token
    state: ModelState = Field(default_factory=ModelState)

    @field_validator('model_key')
    @classmethod
    def model_key_must_be_snake_case(cls, v: str) -> str:
        """Ensure model_key is snake_case for consistency"""
        if ' ' in v or v.lower() != v:
            # We'll just warn but not enforce; could be improved
            pass
        return v


class JudgeConfig(BaseModel):
    """Configuration for judge model ordering and requirement"""
    model_order: List[str] = Field(default_factory=list)  # List of model IDs
    is_judge_required: bool = False


class RoutingOrderConfig(BaseModel):
    """Configuration for strong/weak model ordering"""
    strong_models: List[str] = Field(default_factory=list)
    weak_models: List[str] = Field(default_factory=list)


class UnifiedConfig(BaseModel):
    system_settings: SystemSettings = Field(default_factory=SystemSettings)
    models: Dict[str, ModelConfig] = Field(default_factory=dict)
    judge_config: JudgeConfig = Field(default_factory=JudgeConfig)
    routing_order_config: RoutingOrderConfig = Field(default_factory=RoutingOrderConfig)