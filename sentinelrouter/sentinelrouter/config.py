"""
Configuration management for SentinelRouter.
Loads environment variables with sensible defaults and the unified JSON configuration.
"""

import os
import json
import re
from typing import Optional, Tuple
from pydantic import Field
from pydantic_settings import BaseSettings

from ..schemas.config_models import (
    UnifiedConfig,
    ModelConfig,
    ModelCapabilities,
    RoutingConfig,
    RateLimits,
    TierLimits,
    PricingInfo,
    CostInfo,
    ModelState,
)
from ..schemas.sentinel_config import SentinelConfig, ProviderType


class Settings(BaseSettings):
    """
    Application settings.
    """

    # Provider API keys (required)
    deepseek_api_key: str = Field(..., env="DEEPSEEK_API_KEY")
    anthropic_api_key: str = Field(..., env="ANTHROPIC_API_KEY")
    
    # Gemini API keys (backup models) - defaults removed for security
    gemini_backup1_api_key: str = Field("", env="GEMINI_BACKUP1_API_KEY")
    gemini_backup2_api_key: str = Field("", env="GEMINI_BACKUP2_API_KEY")

    # Model identifiers (kept for backward compatibility)
    weak_model_id: str = Field("deepseek-chat", env="WEAK_MODEL_ID")
    strong_model_id: str = Field("claude-3-opus-20240229", env="STRONG_MODEL_ID")

    # Budget & routing
    max_cost_per_session: float = Field(25.0, env="MAX_COST_PER_SESSION")
    initial_threshold: float = Field(0.9, env="INITIAL_THRESHOLD")
    escalation_rate_limit: float = Field(0.05, env="ESCALATION_RATE_LIMIT")

    # Complexity threshold (for judge)
    complexity_threshold: float = Field(0.5, env="COMPLEXITY_THRESHOLD")

    # Dynamic thresholding
    target_escalation_rate: float = Field(0.05, env="TARGET_ESCALATION_RATE")
    rolling_window_size: int = Field(20, env="ROLLING_WINDOW_SIZE")

    # Cycle detection
    cycle_detection_window_size: int = Field(100, env="CYCLE_DETECTION_WINDOW_SIZE")
    cycle_detection_simhash_threshold: int = Field(3, env="CYCLE_DETECTION_SIMHASH_THRESHOLD")

    # Semantic cache
    semantic_cache_min_samples: int = Field(3, env="SEMANTIC_CACHE_MIN_SAMPLES")
    semantic_cache_confidence_threshold: float = Field(0.75, env="SEMANTIC_CACHE_CONFIDENCE_THRESHOLD")
    semantic_cache_ttl_seconds: int = Field(7 * 24 * 3600, env="SEMANTIC_CACHE_TTL_SECONDS")
    semantic_cache_max_entries: int = Field(10000, env="SEMANTIC_CACHE_MAX_ENTRIES")

    # Database
    database_url: str = Field("sqlite:///./data/sentinelrouter.db", env="DATABASE_URL")
    database_path: str = Field("/data/sentinelrouter.db", env="DATABASE_PATH")

    # Server
    host: str = Field("0.0.0.0", env="HOST")
    port: int = Field(8000, env="PORT")
    log_level: str = Field("INFO", env="LOG_LEVEL")
    log_file: str = Field("./logs/sentinelrouter.log", env="LOG_FILE")
    cors_origins: str = Field("*", env="CORS_ORIGINS")  # Comma-separated list, or "*" for all

    # Logging & Audit
    log_dir: str = Field("logs", env="LOG_DIR")
    enable_file_logging: bool = Field(True, env="ENABLE_FILE_LOGGING")
    log_rotation_max_bytes: int = Field(10 * 1024 * 1024, env="LOG_ROTATION_MAX_BYTES")  # 10 MB
    log_rotation_backup_count: int = Field(5, env="LOG_ROTATION_BACKUP_COUNT")
    log_retention_days: int = Field(30, env="LOG_RETENTION_DAYS")

    # Feature toggles
    enable_budget_killswitch: bool = Field(True, env="ENABLE_BUDGET_KILLSWITCH")
    enable_cycle_detection: bool = Field(True, env="ENABLE_CYCLE_DETECTION")
    enable_dynamic_threshold: bool = Field(True, env="ENABLE_DYNAMIC_THRESHOLD")
    
    # Redaction settings
    redaction_mode: str = Field("logs", env="REDACTION_MODE")  # "none", "logs", or "strict"
    redaction_strategy: str = Field("simple", env="REDACTION_STRATEGY")  # "simple" or "hmac"
    redaction_salt: str = Field("change-me-in-production", env="REDACTION_SALT")  # For HMAC strategy
    redaction_enabled_categories: str = Field("", env="REDACTION_CATEGORIES")  # Comma-separated, empty = all

    # Semantic similarity strategy (for cycle detection and caching)
    semantic_strategy: str = Field("VECTORDB_LOCAL", env="SEMANTIC_STRATEGY")  # "SIMHASH", "VECTORDB_LOCAL", or "VECTORDB_API"
    semantic_similarity_threshold: float = Field(0.85, env="SEMANTIC_SIMILARITY_THRESHOLD")  # 0.0 to 1.0
    semantic_hash_bits: int = Field(64, env="SEMANTIC_HASH_BITS")  # For SIMHASH strategy
    semantic_model_path: str = Field("", env="SEMANTIC_MODEL_PATH")  # Custom ONNX model path for VECTORDB_LOCAL
    semantic_api_key: str = Field("", env="SEMANTIC_API_KEY")  # API key for VECTORDB_API (or uses openai_api_key)
    semantic_api_provider: str = Field("openai", env="SEMANTIC_API_PROVIDER")  # "openai" or "voyage"
    semantic_api_model: str = Field("text-embedding-3-small", env="SEMANTIC_API_MODEL")  # Model name for API
    openai_api_key: str = Field("", env="OPENAI_API_KEY")  # OpenAI API key (for VECTORDB_API fallback)

    # Unified configuration file path
    models_config_path: str = Field("config/models_config.json", env="MODELS_CONFIG_PATH")
    sentinel_config_path: str = Field("config/sentinel_config.json", env="SENTINEL_CONFIG_PATH")

    # Hardcoded prices (per million tokens) - not configurable, defined in clients.py
    # DeepSeek: $0.27 per million tokens
    # Claude Opus: $5.00 per million tokens

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Lazy initialization of settings to avoid validation errors during imports
def get_settings() -> Settings:
    """Return the application settings, initializing if necessary."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance

_settings_instance = None


def get_database_url() -> str:
    """
    Return the database URL, preferring DATABASE_URL if set,
    otherwise constructing from DATABASE_PATH.
    """
    settings = get_settings()
    if settings.database_url:
        return settings.database_url
    return f"sqlite:///{settings.database_path}"


def _resolve_env_placeholders(value):
    """Resolve ${VAR} placeholders in configuration values."""
    if isinstance(value, str):
        pattern = re.compile(r"\$\{([^}]+)\}")

        def replacer(match):
            env_key = match.group(1)
            return os.getenv(env_key, "")

        return pattern.sub(replacer, value)
    if isinstance(value, list):
        return [_resolve_env_placeholders(item) for item in value]
    if isinstance(value, dict):
        return {key: _resolve_env_placeholders(val) for key, val in value.items()}
    return value


def _load_sentinel_config_file(path: str) -> SentinelConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data = _resolve_env_placeholders(data)
    return SentinelConfig(**data)


def load_sentinel_config(path: Optional[str] = None) -> SentinelConfig:
    """Load the SentinelConfig from file with env placeholder resolution."""
    settings = get_settings()
    config_path = path or settings.sentinel_config_path
    return _load_sentinel_config_file(config_path)


def _load_legacy_unified_config() -> UnifiedConfig:
    """
    Load the legacy unified configuration from the JSON file specified in settings.
    If the file does not exist, create a default configuration and write it.
    """
    settings = get_settings()
    path = settings.models_config_path
    if not os.path.exists(path):
        # Ensure the directory exists
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # Create a default configuration with the two main models
        default_config = UnifiedConfig(
            system_settings={},
            models={
                settings.weak_model_id: ModelConfig(
                    display_name="DeepSeek Chat (Weak Tier)",
                    provider="deepseek",
                ),
                settings.strong_model_id: ModelConfig(
                    display_name="Claude 3 Opus (Strong Tier)",
                    provider="anthropic",
                ),
            },
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(default_config.model_dump_json(indent=2))
        return default_config

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return UnifiedConfig(**data)


def _provider_env_value(provider: ProviderType) -> str:
    env_map = {
        ProviderType.DEEPSEEK: "DEEPSEEK_API_KEY",
        ProviderType.ANTHROPIC: "ANTHROPIC_API_KEY",
        ProviderType.GEMINI: "GEMINI_API_KEY",
        ProviderType.GROQ: "GROQ_API_KEY",
        ProviderType.OPENROUTER: "OPENROUTER_API_KEY",
    }
    return os.getenv(env_map.get(provider, ""), "")


def _build_sentinel_config_from_legacy(config: UnifiedConfig) -> SentinelConfig:
    settings = get_settings()
    keys: dict = {}
    key_instances: dict = {}

    provider_instance_map = {}
    for model in config.models.values():
        try:
            provider = ProviderType(model.provider)
        except ValueError:
            continue
        if provider in provider_instance_map:
            continue
        key_id = f"{provider.value}_legacy_key"
        instance_id = f"{provider.value}_legacy_primary"
        keys[key_id] = {
            "type": provider.value,
            "value": _provider_env_value(provider),
        }
        key_instances[instance_id] = {
            "key_ref": key_id,
            "priority": 0,
            "enabled": True,
            "description": f"Legacy primary key for {provider.value}",
        }
        provider_instance_map[provider] = instance_id

    models: dict = {}
    for model_id, model in config.models.items():
        try:
            provider = ProviderType(model.provider)
        except ValueError:
            continue
        instance_id = provider_instance_map.get(provider)
        if not instance_id:
            continue
        models[model_id] = {
            "enabled": model.status == "ACTIVE",
            "provider": provider.value,
            "model_id": model.model_key,
            "key_instance": instance_id,
            "display_name": model.display_name,
            "pricing": {
                "input_cost_per_m": model.pricing.input_cost_per_m,
                "output_cost_per_m": model.pricing.output_cost_per_m,
            },
            "limits": {
                "requests_per_minute": model.limits.requests_per_minute,
                "requests_per_day": model.limits.requests_per_day,
                "tokens_per_minute": model.limits.tokens_per_minute,
            },
        }

    strong_models = list(config.routing_order_config.strong_models)
    weak_models = list(config.routing_order_config.weak_models)

    if not strong_models or not weak_models:
        weak_models = []
        strong_models = []
        for model_id, model in config.models.items():
            if model.routing.priority_group == "strong_tier":
                strong_models.append((model.routing.order, model_id))
            else:
                weak_models.append((model.routing.order, model_id))
        weak_models = [item[1] for item in sorted(weak_models, key=lambda x: x[0])]
        strong_models = [item[1] for item in sorted(strong_models, key=lambda x: x[0])]

    judge_enabled = bool(config.judge_config.model_order) or config.judge_config.is_judge_required
    sentinel_dict = {
        "keys": keys,
        "key_instances": key_instances,
        "models": models,
        "routing_policy": {
            "weak_tier": {"order": weak_models},
            "strong_tier": {"order": strong_models},
        },
        "judge": {
            "enabled": judge_enabled,
            "model_order": list(config.judge_config.model_order),
            "complexity_threshold": settings.complexity_threshold,
        },
        "semantic_cache": {
            "enabled": settings.semantic_cache_min_samples > 0,
            "min_samples": settings.semantic_cache_min_samples,
            "confidence_threshold": settings.semantic_cache_confidence_threshold,
            "ttl_seconds": settings.semantic_cache_ttl_seconds,
        },
    }
    return SentinelConfig(**sentinel_dict)


def _build_unified_config_from_sentinel(
    sentinel_config: SentinelConfig,
    legacy_config: Optional[UnifiedConfig] = None,
) -> UnifiedConfig:
    system_settings = legacy_config.system_settings if legacy_config else {}
    judge_config = {
        "model_order": list(sentinel_config.judge.model_order),
        "is_judge_required": sentinel_config.judge.enabled,
    }
    routing_order_config = {
        "strong_models": list(sentinel_config.routing_policy.strong_tier.order),
        "weak_models": list(sentinel_config.routing_policy.weak_tier.order),
    }

    weak_orders = {
        model_id: idx + 1
        for idx, model_id in enumerate(sentinel_config.routing_policy.weak_tier.order)
    }
    strong_orders = {
        model_id: idx + 1
        for idx, model_id in enumerate(sentinel_config.routing_policy.strong_tier.order)
    }

    models = {}
    for model_id, model in sentinel_config.models.items():
        existing = legacy_config.models.get(model_id) if legacy_config else None
        tokens_per_day = model.limits.tokens_per_minute * 60 * 24
        if model_id in strong_orders:
            priority_group = "strong_tier"
            order = strong_orders[model_id]
        elif model_id in weak_orders:
            priority_group = "fast_tier"
            order = weak_orders[model_id]
        else:
            priority_group = "fast_tier"
            order = 999

        models[model_id] = ModelConfig(
            display_name=model.display_name or model_id,
            provider=model.provider.value,
            model_definition=model.model_id,
            model_key=model.model_id,
            status="ACTIVE" if model.enabled else "BANNED",
            status_valid_till=None,
            capabilities=existing.capabilities if existing else ModelCapabilities(),
            routing=RoutingConfig(priority_group=priority_group, order=order),
            limits=RateLimits(
                requests_per_minute=model.limits.requests_per_minute,
                requests_per_day=model.limits.requests_per_day,
                tokens_per_minute=model.limits.tokens_per_minute,
            ),
            free_tier_limits=TierLimits(
                requests_per_day=model.limits.requests_per_day,
                requests_per_minute=model.limits.requests_per_minute,
                tokens_per_minute=model.limits.tokens_per_minute,
                tokens_per_day=tokens_per_day,
            ),
            paid_tier_limits=TierLimits(
                requests_per_day=model.limits.requests_per_day,
                requests_per_minute=model.limits.requests_per_minute,
                tokens_per_minute=model.limits.tokens_per_minute,
                tokens_per_day=tokens_per_day,
            ),
            pricing=PricingInfo(
                input_cost_per_m=model.pricing.input_cost_per_m,
                output_cost_per_m=model.pricing.output_cost_per_m,
            ),
            cost=existing.cost if existing else CostInfo(),
            state=existing.state if existing else ModelState(),
        )

    return UnifiedConfig(
        system_settings=system_settings,
        models=models,
        judge_config=judge_config,
        routing_order_config=routing_order_config,
    )


def load_unified_config() -> UnifiedConfig:
    """
    Load the unified configuration from the JSON file specified in settings.
    Prefers sentinel_config.json if present, otherwise falls back to models_config.json.
    """
    settings = get_settings()
    if os.path.exists(settings.sentinel_config_path):
        sentinel_config = _load_sentinel_config_file(settings.sentinel_config_path)
        legacy_config = None
        if os.path.exists(settings.models_config_path):
            legacy_config = _load_legacy_unified_config()
        return _build_unified_config_from_sentinel(sentinel_config, legacy_config)
    return _load_legacy_unified_config()


# Global instance of the unified configuration (static part)
_unified_config: Optional[UnifiedConfig] = None


def get_unified_config() -> UnifiedConfig:
    """
    Get the unified configuration (cached).
    """
    global _unified_config
    if _unified_config is None:
        _unified_config = load_unified_config()
    return _unified_config


_runtime_config: Optional[SentinelConfig] = None
_runtime_config_mtime: Optional[float] = None
_runtime_config_source: Optional[str] = None


def get_runtime_config_with_meta(
    reload_if_changed: bool = True,
) -> Tuple[SentinelConfig, bool]:
    """
    Get the runtime SentinelConfig, reloading on file changes when available.

    Returns tuple of (config, changed).
    """
    global _runtime_config, _runtime_config_mtime, _runtime_config_source
    settings = get_settings()
    sentinel_path = settings.sentinel_config_path

    if os.path.exists(sentinel_path):
        mtime = os.path.getmtime(sentinel_path)
        changed = False
        if (
            _runtime_config is None
            or _runtime_config_source != "sentinel"
            or (reload_if_changed and _runtime_config_mtime != mtime)
        ):
            _runtime_config = _load_sentinel_config_file(sentinel_path)
            _runtime_config_mtime = mtime
            _runtime_config_source = "sentinel"
            changed = True
        return _runtime_config, changed

    if _runtime_config is None or _runtime_config_source != "legacy":
        legacy_config = _load_legacy_unified_config()
        _runtime_config = _build_sentinel_config_from_legacy(legacy_config)
        _runtime_config_mtime = None
        _runtime_config_source = "legacy"
        return _runtime_config, True

    return _runtime_config, False


def get_runtime_config(reload_if_changed: bool = True) -> SentinelConfig:
    """Return the runtime SentinelConfig."""
    config, _ = get_runtime_config_with_meta(reload_if_changed=reload_if_changed)
    return config
