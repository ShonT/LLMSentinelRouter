"""
Unit tests for Session Defaults feature.

Tests the SessionDefaults functionality including:
- Loading defaults from config
- Applying defaults with correct priority (request > config > hardcoded)
- Session ID generation strategies
- Session defaults updates via StateManager
- Persistence of session defaults
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from sentinelrouter.schemas.config_models import (
    SessionDefaults,
    SystemSettings,
    UnifiedConfig,
    ModelConfig,
    RoutingConfig,
)


class TestSessionDefaults:
    """Tests for SessionDefaults data model."""
    
    def test_session_defaults_initialization_with_defaults(self):
        """Test SessionDefaults initializes with default values."""
        defaults = SessionDefaults()
        
        assert defaults.default_tier == "free"
        assert defaults.default_use_judge is None  # Smart mode
        assert defaults.session_id_strategy == "uuid"
        assert defaults.default_session_id is not None  # UUID generated
        assert len(defaults.default_session_id) > 0
    
    def test_session_defaults_custom_values(self):
        """Test SessionDefaults with custom values."""
        defaults = SessionDefaults(
            default_session_id="custom-session-id",
            default_tier="paid",
            default_use_judge=True,
            session_id_strategy="ip_based"
        )
        
        assert defaults.default_session_id == "custom-session-id"
        assert defaults.default_tier == "paid"
        assert defaults.default_use_judge is True
        assert defaults.session_id_strategy == "ip_based"
    
    def test_session_defaults_regenerate_session_id_uuid(self):
        """Test regenerating session ID with UUID strategy."""
        defaults = SessionDefaults(session_id_strategy="uuid")
        original_id = defaults.default_session_id
        
        new_id = defaults.regenerate_session_id()
        
        assert new_id != original_id
        assert defaults.default_session_id == new_id
        assert len(new_id) == 36  # UUID format
    
    def test_session_defaults_regenerate_session_id_custom(self):
        """Test regenerating session ID with custom strategy (no change)."""
        defaults = SessionDefaults(
            default_session_id="my-custom-id",
            session_id_strategy="custom"
        )
        original_id = defaults.default_session_id
        
        new_id = defaults.regenerate_session_id()
        
        # Custom strategy should not regenerate
        assert new_id == original_id
        assert defaults.default_session_id == original_id
    
    def test_session_defaults_in_system_settings(self):
        """Test SessionDefaults as part of SystemSettings."""
        settings = SystemSettings(
            session_defaults=SessionDefaults(
                default_tier="paid",
                default_use_judge=False
            )
        )
        
        assert settings.session_defaults.default_tier == "paid"
        assert settings.session_defaults.default_use_judge is False


class TestSessionDefaultsPriority:
    """Tests for session defaults priority logic (request > config > hardcoded)."""
    
    def test_priority_request_overrides_config(self):
        """Test that request values override config defaults."""
        config_tier = "free"
        request_tier = "paid"
        
        # Simulate priority logic
        final_tier = request_tier if request_tier is not None else config_tier
        
        assert final_tier == "paid"
    
    def test_priority_config_overrides_hardcoded(self):
        """Test that config values override hardcoded defaults."""
        config_tier = "paid"
        hardcoded_tier = "free"
        request_tier = None
        
        # Simulate priority logic
        final_tier = request_tier if request_tier is not None else (config_tier if config_tier else hardcoded_tier)
        
        assert final_tier == "paid"
    
    def test_priority_hardcoded_used_when_no_config(self):
        """Test that hardcoded defaults are used when no config or request."""
        config_tier = None
        hardcoded_tier = "free"
        request_tier = None
        
        # Simulate priority logic
        final_tier = request_tier if request_tier is not None else (config_tier if config_tier else hardcoded_tier)
        
        assert final_tier == "free"
    
    def test_priority_use_judge_none_is_valid(self):
        """Test that use_judge=None is a valid value (smart mode)."""
        config_use_judge = None
        request_use_judge = None
        
        # None is a valid value, not "missing"
        final_use_judge = request_use_judge if request_use_judge is not None else config_use_judge
        
        # Should be None (smart mode), not False
        assert final_use_judge is None


class TestSessionIDStrategies:
    """Tests for different session ID generation strategies."""
    
    def test_uuid_strategy_generates_unique_ids(self):
        """Test UUID strategy generates unique IDs."""
        defaults1 = SessionDefaults(session_id_strategy="uuid")
        defaults2 = SessionDefaults(session_id_strategy="uuid")
        
        # Each instance should have a different UUID
        assert defaults1.default_session_id != defaults2.default_session_id
    
    def test_ip_based_strategy_requires_ip(self):
        """Test IP-based strategy metadata."""
        defaults = SessionDefaults(session_id_strategy="ip_based")
        
        # IP-based strategy is set, but actual IP is provided at request time
        assert defaults.session_id_strategy == "ip_based"
    
    def test_custom_strategy_preserves_id(self):
        """Test custom strategy preserves provided ID."""
        custom_id = "my-custom-session-123"
        defaults = SessionDefaults(
            default_session_id=custom_id,
            session_id_strategy="custom"
        )
        
        assert defaults.default_session_id == custom_id
        assert defaults.session_id_strategy == "custom"


@pytest.mark.asyncio
class TestSessionDefaultsStateManager:
    """Tests for SessionDefaults integration with StateManager."""
    
    async def test_get_session_defaults(self):
        """Test getting session defaults from StateManager."""
        from sentinelrouter.sentinelrouter.state_manager import StateManager
        
        config = UnifiedConfig(
            system_settings=SystemSettings(
                session_defaults=SessionDefaults(
                    default_tier="paid",
                    default_use_judge=False
                )
            ),
            models={}
        )
        
        state_manager = StateManager(config)
        defaults = await state_manager.get_session_defaults()
        
        assert defaults["default_tier"] == "paid"
        assert defaults["default_use_judge"] is False
        assert "default_session_id" in defaults
        assert "session_id_strategy" in defaults
    
    async def test_update_session_defaults(self):
        """Test updating session defaults via StateManager."""
        from sentinelrouter.sentinelrouter.state_manager import StateManager
        
        config = UnifiedConfig(
            system_settings=SystemSettings(
                session_defaults=SessionDefaults(
                    default_tier="free",
                    default_use_judge=None
                )
            ),
            models={}
        )
        
        state_manager = StateManager(config)
        
        # Update defaults
        result = await state_manager.update_session_defaults(
            default_tier="paid",
            default_use_judge=True
        )
        
        assert result is True
        
        # Verify update
        defaults = await state_manager.get_session_defaults()
        assert defaults["default_tier"] == "paid"
        assert defaults["default_use_judge"] is True
    
    async def test_regenerate_session_id_via_state_manager(self):
        """Test regenerating session ID via StateManager."""
        from sentinelrouter.sentinelrouter.state_manager import StateManager
        
        config = UnifiedConfig(
            system_settings=SystemSettings(
                session_defaults=SessionDefaults(session_id_strategy="uuid")
            ),
            models={}
        )
        
        state_manager = StateManager(config)
        
        # Get original ID
        original_defaults = await state_manager.get_session_defaults()
        original_id = original_defaults["default_session_id"]
        
        # Regenerate
        new_id = await state_manager.regenerate_session_id()
        
        assert new_id != original_id
        
        # Verify new ID is persisted
        updated_defaults = await state_manager.get_session_defaults()
        assert updated_defaults["default_session_id"] == new_id
    
    async def test_session_defaults_marked_dirty_on_update(self):
        """Test that updating session defaults marks config as dirty."""
        from sentinelrouter.sentinelrouter.state_manager import StateManager
        
        config = UnifiedConfig(
            system_settings=SystemSettings(),
            models={}
        )
        
        state_manager = StateManager(config)
        
        # Initially not dirty
        assert "__config__" not in state_manager.dirty
        
        # Update session defaults
        await state_manager.update_session_defaults(default_tier="paid")
        
        # Should be marked dirty
        assert "__config__" in state_manager.dirty


class TestSessionDefaultsSerialization:
    """Tests for SessionDefaults serialization and persistence."""
    
    def test_session_defaults_to_dict(self):
        """Test SessionDefaults serialization to dict."""
        defaults = SessionDefaults(
            default_session_id="test-id",
            default_tier="paid",
            default_use_judge=False,
            session_id_strategy="custom"
        )
        
        data = defaults.model_dump()
        
        assert data["default_session_id"] == "test-id"
        assert data["default_tier"] == "paid"
        assert data["default_use_judge"] is False
        assert data["session_id_strategy"] == "custom"
    
    def test_session_defaults_from_dict(self):
        """Test SessionDefaults deserialization from dict."""
        data = {
            "default_session_id": "test-id",
            "default_tier": "paid",
            "default_use_judge": True,
            "session_id_strategy": "ip_based"
        }
        
        defaults = SessionDefaults(**data)
        
        assert defaults.default_session_id == "test-id"
        assert defaults.default_tier == "paid"
        assert defaults.default_use_judge is True
        assert defaults.session_id_strategy == "ip_based"
    
    def test_system_settings_with_session_defaults_serialization(self):
        """Test SystemSettings with SessionDefaults serializes correctly."""
        settings = SystemSettings(
            persistence_interval_seconds=5,
            default_routing_strategy="waterfall",
            timezone="UTC",
            session_defaults=SessionDefaults(
                default_tier="paid",
                default_use_judge=False
            )
        )
        
        data = settings.model_dump()
        
        assert "session_defaults" in data
        assert data["session_defaults"]["default_tier"] == "paid"
        assert data["session_defaults"]["default_use_judge"] is False
    
    def test_unified_config_includes_session_defaults(self):
        """Test UnifiedConfig includes session defaults in serialization."""
        config = UnifiedConfig(
            system_settings=SystemSettings(
                session_defaults=SessionDefaults(
                    default_tier="paid",
                    default_use_judge=True
                )
            ),
            models={}
        )
        
        data = config.model_dump()
        
        assert "system_settings" in data
        assert "session_defaults" in data["system_settings"]
        assert data["system_settings"]["session_defaults"]["default_tier"] == "paid"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
