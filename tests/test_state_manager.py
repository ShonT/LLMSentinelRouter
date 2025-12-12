"""
Unit tests for the StateManager (write‑behind persistence).
"""

import asyncio
import json
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
import pytest

from sentinelrouter.sentinelrouter.state_manager import StateManager
from sentinelrouter.schemas.config_models import UnifiedConfig, SystemSettings, ModelConfig, ModelState


@pytest.fixture
def temp_config_file():
    """Create a temporary JSON configuration file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config = UnifiedConfig(
            system_settings=SystemSettings(
                persistence_interval_seconds=1,
                default_routing_strategy="waterfall",
                timezone="UTC"
            ),
            models={
                "test-model-1": ModelConfig(
                    display_name="Test Model 1",
                    provider="test",
                    status="active",
                    routing=ModelConfig.RoutingConfig(priority_group="fast_tier", order=1),
                    limits=ModelConfig.RateLimits(
                        requests_per_minute=10,
                        requests_per_day=1000,
                        tokens_per_minute=500000
                    ),
                    pricing=ModelConfig.PricingInfo(
                        currency="USD",
                        input_cost_per_m=0.0,
                        output_cost_per_m=0.0,
                        usage_tiers=[]
                    ),
                    state=ModelState(
                        current_rpm=0,
                        requests_today=0,
                        tokens_today=0,
                        total_cost_session=0.0,
                        last_updated_ts=None,
                        exhausted_until_ts=None
                    )
                ),
                "test-model-2": ModelConfig(
                    display_name="Test Model 2",
                    provider="test",
                    status="inactive",
                    routing=ModelConfig.RoutingConfig(priority_group="strong_tier", order=1),
                    limits=ModelConfig.RateLimits(
                        requests_per_minute=5,
                        requests_per_day=500,
                        tokens_per_minute=200000
                    ),
                    pricing=ModelConfig.PricingInfo(
                        currency="USD",
                        input_cost_per_m=1.0,
                        output_cost_per_m=2.0,
                        usage_tiers=[]
                    ),
                    state=ModelState(
                        current_rpm=0,
                        requests_today=0,
                        tokens_today=0,
                        total_cost_session=0.0,
                        last_updated_ts=None,
                        exhausted_until_ts=None
                    )
                )
            }
        )
        json.dump(config.dict(exclude_none=True), f)
        yield Path(f.name)
    # Cleanup after test
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
async def state_manager(temp_config_file):
    """Create a StateManager instance with a temporary config file."""
    manager = StateManager(config_path=temp_config_file)
    await manager.start()
    yield manager
    await manager.stop()


@pytest.mark.asyncio
async def test_state_manager_initialization(state_manager):
    """Test that StateManager loads the configuration correctly."""
    assert state_manager is not None
    assert len(state_manager.models) == 2
    assert "test-model-1" in state_manager.models
    assert "test-model-2" in state_manager.models

    model1 = state_manager.models["test-model-1"]
    assert model1.config.display_name == "Test Model 1"
    assert model1.config.status == "active"
    assert model1.config.routing.priority_group == "fast_tier"
    assert model1.state.requests_today == 0


@pytest.mark.asyncio
async def test_get_model_state(state_manager):
    """Test retrieving a model's state."""
    state = await state_manager.get_model_state("test-model-1")
    assert state is not None
    assert isinstance(state, ModelState)
    assert state.requests_today == 0
    assert state.total_cost_session == 0.0


@pytest.mark.asyncio
async def test_update_model_state(state_manager):
    """Test updating a model's state and marking it dirty."""
    before = await state_manager.get_model_state("test-model-1")
    assert before.requests_today == 0

    # Update with new values
    await state_manager.update_model_state(
        "test-model-1",
        requests_today=42,
        total_cost_session=3.14,
        last_updated_ts=datetime.utcnow()
    )

    after = await state_manager.get_model_state("test-model-1")
    assert after.requests_today == 42
    assert after.total_cost_session == 3.14
    assert after.last_updated_ts is not None

    # Verify the model is marked dirty
    assert "test-model-1" in state_manager.dirty_models


@pytest.mark.asyncio
async def test_increment_counter(state_manager):
    """Test incrementing a counter field."""
    initial = await state_manager.get_model_state("test-model-1")
    assert initial.requests_today == 0

    await state_manager.increment_counter("test-model-1", "requests_today", 5)
    after = await state_manager.get_model_state("test-model-1")
    assert after.requests_today == 5

    # Increment again
    await state_manager.increment_counter("test-model-1", "requests_today", 3)
    final = await state_manager.get_model_state("test-model-1")
    assert final.requests_today == 8


@pytest.mark.asyncio
async def test_flush_dirty(state_manager, temp_config_file):
    """Test that dirty models are persisted to disk."""
    # Make a change
    await state_manager.update_model_state(
        "test-model-1",
        requests_today=99,
        last_updated_ts=datetime.utcnow()
    )
    assert "test-model-1" in state_manager.dirty_models

    # Manually trigger flush
    await state_manager._flush_dirty()

    # Verify the file was written
    with open(temp_config_file, 'r') as f:
        saved_config = json.load(f)

    saved_model = saved_config["models"]["test-model-1"]
    assert saved_model["state"]["requests_today"] == 99
    # Dirty set should be cleared
    assert len(state_manager.dirty_models) == 0


@pytest.mark.asyncio
async def test_background_flush(state_manager, temp_config_file):
    """Test that the background task periodically flushes dirty models."""
    # Update a model
    await state_manager.update_model_state(
        "test-model-2",
        requests_today=123,
        last_updated_ts=datetime.utcnow()
    )
    assert "test-model-2" in state_manager.dirty_models

    # Wait a bit more than the flush interval (1 second)
    await asyncio.sleep(1.5)

    # Verify the flush happened
    with open(temp_config_file, 'r') as f:
        saved_config = json.load(f)

    saved_model = saved_config["models"]["test-model-2"]
    assert saved_model["state"]["requests_today"] == 123
    # Dirty set should be empty after flush
    assert len(state_manager.dirty_models) == 0


@pytest.mark.asyncio
async def test_atomic_write(state_manager, temp_config_file):
    """Test that atomic writes use a .tmp file and then rename."""
    # We'll patch the _atomic_write method to inspect, but for simplicity
    # we just verify that after a flush the file is valid JSON.
    await state_manager.update_model_state("test-model-1", requests_today=777)
    await state_manager._flush_dirty()

    # Read the file and check content
    with open(temp_config_file, 'r') as f:
        data = json.load(f)
    assert data["models"]["test-model-1"]["state"]["requests_today"] == 777

    # Also ensure no .tmp file is left behind
    tmp_files = list(temp_config_file.parent.glob("*.tmp"))
    assert len(tmp_files) == 0, f"Temporary files left: {tmp_files}"


@pytest.mark.asyncio
async def test_get_all_models(state_manager):
    """Test retrieving all models."""
    all_models = await state_manager.get_all_models()
    assert isinstance(all_models, dict)
    assert len(all_models) == 2
    assert "test-model-1" in all_models
    assert "test-model-2" in all_models

    model1 = all_models["test-model-1"]
    assert model1.config.display_name == "Test Model 1"
    assert model1.state.requests_today == 0


def test_state_manager_singleton():
    """Test that get_state_manager returns a singleton instance."""
    import asyncio
    from sentinelrouter.sentinelrouter.state_manager import get_state_manager

    async def test():
        manager1 = await get_state_manager()
        manager2 = await get_state_manager()
        assert manager1 is manager2

    asyncio.run(test())