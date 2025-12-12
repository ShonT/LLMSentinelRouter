"""
Unit tests for the new Pydantic configuration models.
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from sentinelrouter.schemas.config_models import (
    SystemSettings,
    ModelCapabilities,
    RoutingConfig,
    RateLimits,
    PricingTier,
    PricingInfo,
    ModelState,
    TierLimits,
    CostInfo,
    JudgeConfig,
    RoutingOrderConfig,
    ModelConfig,
    UnifiedConfig,
)


def test_system_settings():
    """Test SystemSettings validation."""
    settings = SystemSettings(
        persistence_interval_seconds=5,
        default_routing_strategy="waterfall",
        timezone="UTC"
    )
    assert settings.persistence_interval_seconds == 5
    assert settings.default_routing_strategy == "waterfall"
    assert settings.timezone == "UTC"

    # Invalid interval
    with pytest.raises(ValidationError):
        SystemSettings(persistence_interval_seconds=-1)


def test_model_capabilities():
    """Test ModelCapabilities validation."""
    caps = ModelCapabilities(
        modality=["text", "image"],
        context_window=128000
    )
    assert "text" in caps.modality
    assert caps.context_window == 128000

    # Invalid modality type
    with pytest.raises(ValidationError):
        ModelCapabilities(modality=["video"])  # Not in allowed list


def test_routing_config():
    """Test RoutingConfig validation."""
    rc = RoutingConfig(
        priority_group="fast_tier",
        order=1
    )
    assert rc.priority_group == "fast_tier"
    assert rc.order == 1

    # Invalid priority group
    with pytest.raises(ValidationError):
        RoutingConfig(priority_group="unknown")


def test_rate_limits():
    """Test RateLimits validation."""
    limits = RateLimits(
        requests_per_minute=15,
        requests_per_day=1500,
        tokens_per_minute=1000000
    )
    assert limits.requests_per_minute == 15
    assert limits.requests_per_day == 1500
    assert limits.tokens_per_minute == 1000000

    # Negative values not allowed
    with pytest.raises(ValidationError):
        RateLimits(requests_per_minute=-5)


def test_pricing_tier():
    """Test PricingTier validation."""
    tier = PricingTier(
        name="Free Tier",
        threshold_requests=1500,
        input_cost=0.0,
        output_cost=0.0
    )
    assert tier.name == "Free Tier"
    assert tier.threshold_requests == 1500
    assert tier.input_cost == 0.0
    assert tier.output_cost == 0.0

    # 'inf' as string is allowed for threshold_requests
    tier_inf = PricingTier(
        name="Unlimited",
        threshold_requests="inf",
        input_cost=0.5,
        output_cost=1.0
    )
    assert tier_inf.threshold_requests == "inf"


def test_pricing_info():
    """Test PricingInfo validation."""
    pricing = PricingInfo(
        currency="USD",
        input_cost_per_m=0.35,
        output_cost_per_m=0.70,
        usage_tiers=[
            PricingTier(name="Tier 1", threshold_requests=1000, input_cost=0.0, output_cost=0.0),
            PricingTier(name="Tier 2", threshold_requests="inf", input_cost=0.5, output_cost=1.0),
        ]
    )
    assert pricing.currency == "USD"
    assert pricing.input_cost_per_m == 0.35
    assert len(pricing.usage_tiers) == 2


def test_model_state():
    """Test ModelState validation."""
    now = datetime.utcnow()
    state = ModelState(
        current_rpm=12.5,
        requests_today=42,
        tokens_today=15000,
        total_cost_session=3.1415,
        last_updated_ts=now,
        exhausted_until_ts=None
    )
    assert state.current_rpm == 12.5
    assert state.requests_today == 42
    assert state.last_updated_ts == now

    # Negative counts are not allowed
    with pytest.raises(ValidationError):
        ModelState(requests_today=-1)


def test_tier_limits_and_cost_info():
    """Test TierLimits and CostInfo validation."""
    # TierLimits
    tier = TierLimits(
        requests_per_day=1500,
        requests_per_minute=15,
        tokens_per_minute=1_000_000,
        tokens_per_day=10_000_000,
    )
    assert tier.requests_per_day == 1500
    assert tier.tokens_per_minute == 1_000_000
    # Negative values not allowed
    with pytest.raises(ValidationError):
        TierLimits(requests_per_day=-1)
    
    # CostInfo
    cost = CostInfo(per_call=0.01, per_token_input=0.000002, per_token_output=0.000004)
    assert cost.per_call == 0.01
    assert cost.per_token_input == 0.000002
    assert cost.per_token_output == 0.000004
    # Negative cost not allowed
    with pytest.raises(ValidationError):
        CostInfo(per_call=-0.01)


def test_judge_config_and_routing_order_config():
    """Test JudgeConfig and RoutingOrderConfig validation."""
    # JudgeConfig
    judge = JudgeConfig(model_order=["model1", "model2"], is_judge_required=True)
    assert judge.model_order == ["model1", "model2"]
    assert judge.is_judge_required is True
    
    # RoutingOrderConfig
    routing = RoutingOrderConfig(
        strong_models=["claude-3-opus", "gpt-4"],
        weak_models=["deepseek-chat", "gemini-flash"],
    )
    assert routing.strong_models == ["claude-3-opus", "gpt-4"]
    assert routing.weak_models == ["deepseek-chat", "gemini-flash"]


def test_model_config():
    """Test ModelConfig validation."""
    config = ModelConfig(
        display_name="Test Model",
        provider="anthropic",
        model_definition="A test model",
        model_key="anthropic-claude-3",
        status="active",
        status_valid_till=None,
        capabilities=ModelCapabilities(modality=["text"], context_window=128000),
        routing=RoutingConfig(priority_group="fast_tier", order=1),
        limits=RateLimits(requests_per_minute=10, requests_per_day=1000, tokens_per_minute=500000),
        free_tier_limits=TierLimits(requests_per_day=100, requests_per_minute=5, tokens_per_minute=100000, tokens_per_day=500000),
        paid_tier_limits=TierLimits(requests_per_day=5000, requests_per_minute=50, tokens_per_minute=2000000, tokens_per_day=10000000),
        pricing=PricingInfo(
            currency="USD",
            input_cost_per_m=0.0,
            output_cost_per_m=0.0,
            usage_tiers=[]
        ),
        cost=CostInfo(per_call=0.01, per_token_input=0.000002, per_token_output=0.000004),
        state=ModelState()
    )
    assert config.display_name == "Test Model"
    assert config.model_definition == "A test model"
    assert config.model_key == "anthropic-claude-3"
    assert config.status == "active"
    assert config.status_valid_till is None
    assert config.routing.priority_group == "fast_tier"
    assert config.free_tier_limits.requests_per_day == 100
    assert config.paid_tier_limits.tokens_per_minute == 2000000
    assert config.cost.per_call == 0.01

    # Invalid status
    with pytest.raises(ValidationError):
        ModelConfig(
            display_name="Test",
            provider="test",
            model_key="test",
            status="invalid",
            capabilities=ModelCapabilities(modality=["text"], context_window=1000),
            routing=RoutingConfig(priority_group="fast_tier", order=1),
            limits=RateLimits(requests_per_minute=10, requests_per_day=1000, tokens_per_minute=500000),
            pricing=PricingInfo(currency="USD", input_cost_per_m=0.0, output_cost_per_m=0.0, usage_tiers=[]),
            state=ModelState()
        )


def test_unified_config():
    """Test UnifiedConfig validation."""
    config = UnifiedConfig(
        system_settings=SystemSettings(),
        models={
            "model-1": ModelConfig(
                display_name="Model One",
                provider="deepseek",
                model_key="deepseek-chat",
                status="active",
                capabilities=ModelCapabilities(modality=["text"], context_window=128000),
                routing=RoutingConfig(priority_group="fast_tier", order=1),
                limits=RateLimits(requests_per_minute=10, requests_per_day=1000, tokens_per_minute=500000),
                pricing=PricingInfo(currency="USD", input_cost_per_m=0.0, output_cost_per_m=0.0, usage_tiers=[]),
                state=ModelState()
            )
        }
    )
    assert len(config.models) == 1
    assert config.system_settings.persistence_interval_seconds == 5  # default


def test_unified_config_serialization():
    """Test that UnifiedConfig can be serialized to dict and JSON."""
    config = UnifiedConfig(
        system_settings=SystemSettings(),
        models={
            "test": ModelConfig(
                display_name="Test",
                provider="test",
                model_key="test-model",
                status="active",
                capabilities=ModelCapabilities(modality=["text"], context_window=1000),
                routing=RoutingConfig(priority_group="fast_tier", order=1),
                limits=RateLimits(requests_per_minute=10, requests_per_day=1000, tokens_per_minute=500000),
                pricing=PricingInfo(currency="USD", input_cost_per_m=0.0, output_cost_per_m=0.0, usage_tiers=[]),
                state=ModelState()
            )
        }
    )
    data = config.dict()
    assert "system_settings" in data
    assert "models" in data
    assert data["models"]["test"]["display_name"] == "Test"

    # Ensure JSON serialization works
    import json
    json_str = config.json()
    loaded = UnifiedConfig.parse_raw(json_str)
    assert loaded.models["test"].display_name == "Test"