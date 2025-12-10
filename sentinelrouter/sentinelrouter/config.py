"""
Configuration management for SentinelRouter.
Loads environment variables with sensible defaults.
"""

import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings.
    """

    # Provider API keys (required)
    deepseek_api_key: str = Field(..., env="DEEPSEEK_API_KEY")
    anthropic_api_key: str = Field(..., env="ANTHROPIC_API_KEY")

    # Model identifiers
    weak_model_id: str = Field("deepseek-chat", env="WEAK_MODEL_ID")
    strong_model_id: str = Field("claude-3-opus-20240229", env="STRONG_MODEL_ID")

    # Budget & routing
    max_cost_per_session: float = Field(10.0, env="MAX_COST_PER_SESSION")
    initial_threshold: float = Field(0.7, env="INITIAL_THRESHOLD")
    escalation_rate_limit: float = Field(0.05, env="ESCALATION_RATE_LIMIT")

    # Complexity threshold (for judge)
    complexity_threshold: float = Field(0.5, env="COMPLEXITY_THRESHOLD")

    # Dynamic thresholding
    target_escalation_rate: float = Field(0.05, env="TARGET_ESCALATION_RATE")
    rolling_window_size: int = Field(20, env="ROLLING_WINDOW_SIZE")

    # Cycle detection
    cycle_detection_window_size: int = Field(100, env="CYCLE_DETECTION_WINDOW_SIZE")
    cycle_detection_simhash_threshold: int = Field(3, env="CYCLE_DETECTION_SIMHASH_THRESHOLD")

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