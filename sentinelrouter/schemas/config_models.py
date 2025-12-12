"""
Pydantic models for the unified configuration schema.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, List, Literal, Optional, Union
from datetime import datetime


class SystemSettings(BaseModel):
    persistence_interval_seconds: int = 5
    default_routing_strategy: Literal["waterfall", "priority"] = "waterfall"
    timezone: str = "UTC"


class ModelCapabilities(BaseModel):
    modality: List[Literal["text", "image", "audio"]] = ["text"]
    context_window: int = 128000


class RoutingConfig(BaseModel):
    priority_group: Literal["fast_tier", "strong_tier"] = "fast_tier"
    order: int = 1


class RateLimits(BaseModel):
    requests_per_minute: int = 15
    requests_per_day: int = 1500
    tokens_per_minute: int = 1_000_000


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
    current_rpm: int = 0
    requests_today: int = 0
    tokens_today: int = 0
    total_cost_session: float = 0.0
    last_updated_ts: Optional[datetime] = None
    exhausted_until_ts: Optional[datetime] = None


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str
    provider: str
    status: Literal["active", "inactive", "disabled"] = "active"
    capabilities: ModelCapabilities = Field(default_factory=ModelCapabilities)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    limits: RateLimits = Field(default_factory=RateLimits)
    pricing: PricingInfo = Field(default_factory=PricingInfo)
    state: ModelState = Field(default_factory=ModelState)


class UnifiedConfig(BaseModel):
    system_settings: SystemSettings = Field(default_factory=SystemSettings)
    models: Dict[str, ModelConfig] = Field(default_factory=dict)