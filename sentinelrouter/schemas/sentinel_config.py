"""
New Pydantic configuration schema for SentinelRouter.
Implements operator-grade validation with referential integrity checks.
"""

from pydantic import BaseModel, Field, model_validator
from typing import Dict, List, Literal, Optional
from enum import Enum
import warnings


# ============================================================================
# Provider Types
# ============================================================================

class ProviderType(str, Enum):
    """Supported LLM provider types."""
    GROQ = "groq"
    OPENROUTER = "openrouter"
    DEEPSEEK = "deepseek"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


# ============================================================================
# Key Management
# ============================================================================

class Key(BaseModel):
    """
    A credential (API key) for a provider.
    Keys are stored separately and referenced by KeyInstances.
    """
    type: ProviderType = Field(
        ...,
        description="Provider type this key authenticates with.",
    )
    
    value: str = Field(
        ...,
        description="The API key value. Should be managed securely (env vars).",
    )


class KeyInstance(BaseModel):
    """
    A named reference to a key, allowing multiple instances per provider.
    Example: 'groq_primary', 'groq_backup' both reference different keys.
    """
    key_ref: str = Field(
        ...,
        description="Reference to a key ID in the keys dictionary.",
    )

    priority: int = Field(
        0,
        ge=0,
        description="Priority order for this key instance (lower is higher priority).",
    )
    
    enabled: bool = Field(
        True,
        description="Whether this key instance can be used for routing.",
    )
    
    description: Optional[str] = Field(
        None,
        description="Human-readable description of this key instance.",
    )


# ============================================================================
# Pricing and Limits
# ============================================================================

class Pricing(BaseModel):
    """
    Pricing configuration for a model.
    All costs are per million tokens.
    """
    input_cost_per_m: float = Field(
        0.0,
        ge=0.0,
        description="Cost per million input tokens (USD).",
    )
    
    output_cost_per_m: float = Field(
        0.0,
        ge=0.0,
        description="Cost per million output tokens (USD).",
    )


class Limits(BaseModel):
    """
    Local rate limits enforced by SentinelRouter.
    These protect against hitting provider limits.
    """
    requests_per_minute: int = Field(
        ...,
        ge=0,
        description="Maximum requests per minute for this model.",
    )
    
    requests_per_day: int = Field(
        ...,
        ge=0,
        description="Maximum requests per day for this model.",
    )
    
    tokens_per_minute: int = Field(
        ...,
        ge=0,
        description="Maximum tokens per minute for this model.",
    )


# ============================================================================
# Model Definition
# ============================================================================

class ModelDefinition(BaseModel):
    """
    A concrete executable model definition.
    A model is uniquely identified by (provider, model_id, key_instance[s]).
    """
    enabled: bool = Field(
        True,
        description=(
            "Whether this model is eligible for routing and judging. "
            "Disabling a model removes it from consideration without "
            "deleting configuration."
        ),
    )

    provider: ProviderType = Field(
        ...,
        description="LLM provider for this model (must match key type).",
    )

    model_id: str = Field(
        ...,
        description="Provider-specific model identifier.",
    )

    key_instance: Optional[str] = Field(
        None,
        description=(
            "Single key instance used to authenticate requests for this model. "
            "Deprecated in favor of key_instances for priority-based failover."
        ),
    )
    
    key_instances: Optional[List[str]] = Field(
        None,
        description=(
            "Ordered list of key instances for priority-based selection and failover. "
            "If omitted, key_instance is used."
        ),
    )

    pricing: Pricing = Field(
        ...,
        description="Pricing configuration for cost accounting. Mandatory.",
    )

    limits: Limits = Field(
        ...,
        description="Local rate limits enforced by SentinelRouter. Mandatory.",
    )
    
    display_name: Optional[str] = Field(
        None,
        description="Human-readable display name for dashboard/logs.",
    )


# ============================================================================
# Routing Configuration
# ============================================================================

class RoutingTier(BaseModel):
    """
    A routing tier defines an ordered list of models to try.
    Models are attempted in order until one succeeds or budget is exceeded.
    """
    order: List[str] = Field(
        ...,
        description="Ordered list of model IDs to try in this tier.",
    )


class RoutingPolicy(BaseModel):
    """
    Defines routing strategy with weak (fast/cheap) and strong (slow/expensive) tiers.
    """
    weak_tier: RoutingTier = Field(
        ...,
        description="Fast/cheap models attempted first.",
    )
    
    strong_tier: RoutingTier = Field(
        ...,
        description="Slow/expensive models used when weak tier fails or escalates.",
    )


# ============================================================================
# Judge Configuration
# ============================================================================

class JudgeConfig(BaseModel):
    """
    Configuration for the judge system.
    The judge evaluates responses and makes escalation decisions.
    """
    enabled: bool = Field(
        False,
        description="Whether the judge system is active.",
    )
    
    model_order: List[str] = Field(
        default_factory=list,
        description=(
            "Ordered list of model IDs to use as judges. "
            "First available model in the list will be used."
        ),
    )
    
    complexity_threshold: float = Field(
        0.5,
        ge=0.0,
        le=1.0,
        description="Threshold for classifying queries as complex (0.0-1.0).",
    )


# ============================================================================
# Semantic Cache Configuration
# ============================================================================

class SemanticCacheConfig(BaseModel):
    """
    Configuration for semantic similarity caching.
    Caches routing decisions for similar queries.
    """
    enabled: bool = Field(
        False,
        description="Whether semantic caching is active.",
    )
    
    min_samples: int = Field(
        3,
        ge=1,
        description="Minimum samples needed before cache entry is considered reliable.",
    )
    
    confidence_threshold: float = Field(
        0.75,
        ge=0.0,
        le=1.0,
        description="Confidence threshold for using cached routing decision.",
    )
    
    ttl_seconds: int = Field(
        604800,  # 7 days
        ge=0,
        description="Time-to-live for cache entries in seconds.",
    )


# ============================================================================
# Main Configuration
# ============================================================================

class SentinelConfig(BaseModel):
    """
    Complete SentinelRouter configuration.
    Validated at load time with referential integrity checks.
    """
    
    # Core configuration sections
    keys: Dict[str, Key] = Field(
        ...,
        description="API keys indexed by key ID.",
    )
    
    key_instances: Dict[str, KeyInstance] = Field(
        ...,
        description="Named key instances that reference keys.",
    )
    
    models: Dict[str, ModelDefinition] = Field(
        ...,
        description="Model definitions indexed by model ID.",
    )
    
    routing_policy: RoutingPolicy = Field(
        ...,
        description="Routing configuration with weak and strong tiers.",
    )
    
    judge: JudgeConfig = Field(
        default_factory=JudgeConfig,
        description="Judge system configuration.",
    )
    
    semantic_cache: SemanticCacheConfig = Field(
        default_factory=SemanticCacheConfig,
        description="Semantic cache configuration.",
    )

    @model_validator(mode="after")
    def validate_sentinel_integrity(self) -> "SentinelConfig":
        """
        Comprehensive validation ensuring referential integrity and policy correctness.
        """
        # ------------------------------------------------------------------
        # 1. Validate KeyInstance → Key references
        # ------------------------------------------------------------------
        for ki_id, inst in self.key_instances.items():
            if inst.key_ref not in self.keys:
                raise ValueError(
                    f"KeyInstance '{ki_id}' refers to missing key '{inst.key_ref}'"
                )

        # ------------------------------------------------------------------
        # 2. Validate Model → KeyInstance references and provider type safety
        # ------------------------------------------------------------------
        for model_id, model in self.models.items():
            if model.key_instances:
                instance_ids = model.key_instances
            elif model.key_instance:
                instance_ids = [model.key_instance]
                model.key_instances = instance_ids
            else:
                raise ValueError(
                    f"Model '{model_id}' must define key_instance or key_instances"
                )

            if len(set(instance_ids)) != len(instance_ids):
                raise ValueError(
                    f"Model '{model_id}' has duplicate key_instances: {instance_ids}"
                )

            enabled_instances = 0
            for instance_id in instance_ids:
                if instance_id not in self.key_instances:
                    raise ValueError(
                        f"Model '{model_id}' refers to missing key_instance '{instance_id}'"
                    )

                instance = self.key_instances[instance_id]
                if instance.enabled:
                    enabled_instances += 1

                key_ref = instance.key_ref
                key_type = self.keys[key_ref].type

                if model.provider != key_type:
                    raise ValueError(
                        f"Model '{model_id}' provider '{model.provider}' does not match "
                        f"key '{key_ref}' provider '{key_type}'"
                    )

            if model.enabled and enabled_instances == 0:
                raise ValueError(
                    f"Model '{model_id}' has no enabled key_instances"
                )

        # ------------------------------------------------------------------
        # 3. Validate routing tiers are non-empty
        # ------------------------------------------------------------------
        if not self.routing_policy.weak_tier.order:
            raise ValueError("routing_policy.weak_tier.order must not be empty")

        if not self.routing_policy.strong_tier.order:
            raise ValueError("routing_policy.strong_tier.order must not be empty")

        # ------------------------------------------------------------------
        # 4. Validate routing tiers refer to existing, enabled models
        # ------------------------------------------------------------------
        for tier_name, tier in [
            ("weak_tier", self.routing_policy.weak_tier),
            ("strong_tier", self.routing_policy.strong_tier),
        ]:
            for model_id in tier.order:
                if model_id not in self.models:
                    raise ValueError(
                        f"routing_policy.{tier_name} refers to missing model '{model_id}'"
                    )
                if not self.models[model_id].enabled:
                    raise ValueError(
                        f"routing_policy.{tier_name} refers to disabled model '{model_id}'"
                    )

        # ------------------------------------------------------------------
        # 5. Prevent overlap between weak and strong tiers
        # ------------------------------------------------------------------
        weak_set = set(self.routing_policy.weak_tier.order)
        strong_set = set(self.routing_policy.strong_tier.order)
        overlap = weak_set & strong_set

        if overlap:
            raise ValueError(
                f"Models cannot appear in both weak and strong tiers: {sorted(overlap)}"
            )

        # ------------------------------------------------------------------
        # 6. Validate Judge configuration
        # ------------------------------------------------------------------
        if self.judge.enabled:
            if not self.judge.model_order:
                raise ValueError(
                    "judge.enabled is True but judge.model_order is empty"
                )

            for model_id in self.judge.model_order:
                if model_id not in self.models:
                    raise ValueError(
                        f"judge.model_order refers to missing model '{model_id}'"
                    )
                if not self.models[model_id].enabled:
                    raise ValueError(
                        f"judge.model_order refers to disabled model '{model_id}'"
                    )

        # ------------------------------------------------------------------
        # 7. Semantic cache + judge interaction warning
        # ------------------------------------------------------------------
        if self.semantic_cache.enabled and not self.judge.enabled:
            # This is intentionally NOT a hard error.
            # Semantic cache can function without judge, but only if
            # historical routing data already exists.
            warnings.warn(
                "semantic_cache.enabled=True while judge.enabled=False. "
                "Semantic cache will not learn new routing decisions without "
                "an active judge. This is safe but typically unintended.",
                UserWarning,
            )

        return self
