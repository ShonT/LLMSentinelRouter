"""
Configuration management for SentinelRouter.
Loads environment variables with sensible defaults and the unified JSON configuration.
"""

import os
import json
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings

from ..schemas.config_models import UnifiedConfig, ModelConfig


class Settings(BaseSettings):
    """
    Application settings.
    """

    # Provider API keys (required)
    deepseek_api_key: str = Field(..., env="DEEPSEEK_API_KEY")
    anthropic_api_key: str = Field(..., env="ANTHROPIC_API_KEY")
    
    # Gemini API keys (backup models)
    gemini_backup1_api_key: str = Field("AIzaSyCmm7euC6vHz39nJXEZAkqqJeUIB1rtVI8", env="GEMINI_BACKUP1_API_KEY")
    gemini_backup2_api_key: str = Field("AIzaSyBEgIiciMs-NIQqeoYtOfjkvCzVIAr5Fw8", env="GEMINI_BACKUP2_API_KEY")

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

    # Unified configuration file path
    models_config_path: str = Field("config/models_config.json", env="MODELS_CONFIG_PATH")

    # Hardcoded prices (per million tokens) - not configurable, defined in clients.py
    # DeepSeek: $0.27 per million tokens
    # Claude Opus: $5.00 per million tokens

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()


def get_database_url() -> str:
    """
    Return the database URL, preferring DATABASE_URL if set,
    otherwise constructing from DATABASE_PATH.
    """
    if settings.database_url:
        return settings.database_url
    return f"sqlite:///{settings.database_path}"


def load_unified_config() -> UnifiedConfig:
    """
    Load the unified configuration from the JSON file specified in settings.
    If the file does not exist, create a default configuration and write it.
    """
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
