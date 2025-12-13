"""
State Manager with write‑behind persistence.

Holds the unified configuration in memory, tracks dirty state, and periodically
flushes changes to disk using atomic writes.
"""

import asyncio
import json
import logging
import os
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Dict, Set, Optional, Any, Union

from .config import get_unified_config, settings
from ..schemas.config_models import (
    UnifiedConfig,
    ModelConfig,
    ModelState,
    JudgeConfig,
    RoutingOrderConfig,
)

logger = logging.getLogger(__name__)


class StateManager:
    """
    Manages in‑memory model state with write‑behind persistence.

    Attributes:
        config: The current unified configuration (immutable part).
        dirty: Set of model IDs that have been modified since last flush.
        lock: asyncio.Lock for thread‑safe mutations.
        task: Background task that runs the periodic flush.
        stop_event: Event to signal the background task to stop.
    """

    def __init__(self, config: UnifiedConfig):
        self.config = config
        self.dirty: Set[str] = set()
        self.lock = asyncio.Lock()
        self.task: Optional[asyncio.Task] = None
        self.stop_event = asyncio.Event()

    def start(self) -> None:
        """Start the background flush task."""
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._flush_loop())
            logger.info("StateManager background flush task started")

    async def stop(self) -> None:
        """Stop the background flush task and perform a final flush."""
        self.stop_event.set()
        if self.task and not self.task.done():
            await self.task
        # Final flush to ensure no dirty data is lost
        await self._flush_dirty()
        logger.info("StateManager stopped")

    async def _flush_loop(self) -> None:
        """Background loop that flushes dirty state every N seconds."""
        interval = self.config.system_settings.persistence_interval_seconds
        while not self.stop_event.is_set():
            await asyncio.sleep(interval)
            await self._flush_dirty()

    async def _flush_dirty(self) -> None:
        """
        Flush all dirty model states to disk.

        This method:
          1. Acquires the lock and copies the dirty set.
          2. Writes the entire config to a temporary file.
          3. Atomically renames the temporary file to the target path.
          4. Clears the dirty set.
        """
        async with self.lock:
            if not self.dirty:
                return
            dirty_copy = set(self.dirty)
            self.dirty.clear()

        try:
            # Write the entire config (not just dirty models) to ensure consistency
            await self._atomic_write()
            logger.debug(
                f"Flushed dirty models {dirty_copy} to {settings.models_config_path}"
            )
        except Exception as e:
            # Re-add dirty models because the write failed
            async with self.lock:
                self.dirty.update(dirty_copy)
            logger.error(f"Failed to flush dirty state: {e}")

    async def _atomic_write(self) -> None:
        """Write the current config to disk atomically."""
        target_path = settings.models_config_path
        # Create a temporary file in the same directory for atomic rename
        temp_fd, temp_path = tempfile.mkstemp(
            suffix=".tmp", dir=os.path.dirname(target_path), text=True
        )
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(self.config.model_dump(), f, indent=2, default=str)
            # Atomic rename (POSIX guarantee)
            os.replace(temp_path, target_path)
        except Exception:
            # If anything goes wrong, clean up the temporary file
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    async def get_model_config(self, model_id: str) -> Optional[ModelConfig]:
        """Return the configuration for a model (read‑only)."""
        return self.config.models.get(model_id)

    async def get_model_state(self, model_id: str) -> Optional[ModelState]:
        """Return the current state of a model (read‑only)."""
        model = self.config.models.get(model_id)
        return model.state if model else None

    async def update_model_state(
        self, model_id: str, **updates: Dict[str, Any]
    ) -> bool:
        """
        Update the state of a model and mark it as dirty.

        Updates are applied to the ModelState object. Only fields that exist
        in ModelState can be updated.

        Returns True if the update succeeded, False if the model does not exist.
        """
        async with self.lock:
            model = self.config.models.get(model_id)
            if model is None:
                logger.warning(f"Attempted to update non‑existent model {model_id}")
                return False

            # Apply updates to the state
            state_dict = model.state.model_dump()
            for key, value in updates.items():
                if key in state_dict:
                    state_dict[key] = value
                else:
                    logger.warning(
                        f"Ignoring invalid state field '{key}' for model {model_id}"
                    )
            # Create a new ModelState instance
            new_state = ModelState(**state_dict)
            # Replace the model's state (ModelConfig is immutable, so we must replace the whole model)
            # We create a new ModelConfig with the updated state and all other fields
            updated_model = ModelConfig(
                display_name=model.display_name,
                provider=model.provider,
                model_definition=model.model_definition,
                model_key=model.model_key,
                status=model.status,
                status_valid_till=model.status_valid_till,
                capabilities=model.capabilities,
                routing=model.routing,
                limits=model.limits,
                free_tier_limits=model.free_tier_limits,
                paid_tier_limits=model.paid_tier_limits,
                pricing=model.pricing,
                cost=model.cost,
                state=new_state,
            )
            self.config.models[model_id] = updated_model
            self.dirty.add(model_id)
            logger.debug(f"Updated state for model {model_id}, marked dirty")
            return True

    async def increment_counter(
        self, model_id: str, counter: str, amount: Union[int, float] = 1
    ) -> bool:
        """
        Increment a numeric counter in the model's state (e.g., requests_today).

        This is a convenience method that updates the counter and marks the model dirty.
        """
        current_state = await self.get_model_state(model_id)
        if current_state is None:
            return False

        current_value = getattr(current_state, counter, None)
        if isinstance(current_value, (int, float)):
            new_value = current_value + amount
            return await self.update_model_state(model_id, **{counter: new_value})
        else:
            logger.error(
                f"Cannot increment non‑numeric counter {counter} for model {model_id}"
            )
            return False

    async def get_all_models(self) -> Dict[str, ModelConfig]:
        """Return a copy of all model configurations (read‑only)."""
        return dict(self.config.models)

    async def get_dirty_count(self) -> int:
        """Return the number of currently dirty models."""
        async with self.lock:
            return len(self.dirty)

    async def force_flush(self) -> None:
        """Immediately flush all dirty models to disk."""
        await self._flush_dirty()

    async def add_model(self, model_id: str, model_config: ModelConfig) -> bool:
        """Add a new model to the configuration."""
        async with self.lock:
            if model_id in self.config.models:
                logger.warning(f"Model {model_id} already exists")
                return False
            self.config.models[model_id] = model_config
            self.dirty.add(model_id)
            logger.info(f"Added model {model_id}")
            return True

    async def delete_model(self, model_id: str) -> bool:
        """
        Soft delete a model by marking it as BANNED.
        
        This preserves the model in historical logs and routing decisions
        while preventing it from being used for new requests.
        """
        async with self.lock:
            if model_id not in self.config.models:
                logger.warning(f"Model {model_id} does not exist")
                return False
            
            # Soft delete: mark as BANNED instead of removing
            self.config.models[model_id].status = "BANNED"
            self.config.models[model_id].status_valid_till = None  # Permanent ban
            self.dirty.add(model_id)
            logger.info(f"Soft-deleted model {model_id} (marked as BANNED)")
            return True

    async def update_model_config(self, model_id: str, **updates) -> bool:
        """Update the configuration of a model (excluding state)."""
        async with self.lock:
            model = self.config.models.get(model_id)
            if model is None:
                logger.warning(f"Model {model_id} does not exist")
                return False
            # Create a new model config with updates
            model_dict = model.model_dump()
            for key, value in updates.items():
                if key in model_dict:
                    model_dict[key] = value
                else:
                    logger.warning(f"Ignoring unknown field {key} for model {model_id}")
            # Reconstruct ModelConfig
            updated_model = ModelConfig(**model_dict)
            self.config.models[model_id] = updated_model
            self.dirty.add(model_id)
            logger.debug(f"Updated config for model {model_id}")
            return True

    async def ban_model(self, model_id: str, until: Optional[datetime] = None) -> bool:
        """Ban a model until a given datetime (or indefinitely if None)."""
        async with self.lock:
            model = self.config.models.get(model_id)
            if model is None:
                logger.warning(f"Model {model_id} does not exist")
                return False
            model_dict = model.model_dump()
            model_dict["status"] = "BANNED"
            model_dict["status_valid_till"] = until
            updated_model = ModelConfig(**model_dict)
            self.config.models[model_id] = updated_model
            self.dirty.add(model_id)
            logger.info(f"Banned model {model_id} until {until}")
            return True

    async def unban_model(self, model_id: str) -> bool:
        """Remove ban from a model, setting status to active."""
        async with self.lock:
            model = self.config.models.get(model_id)
            if model is None:
                logger.warning(f"Model {model_id} does not exist")
                return False
            model_dict = model.model_dump()
            model_dict["status"] = "ACTIVE"
            model_dict["status_valid_till"] = None
            updated_model = ModelConfig(**model_dict)
            self.config.models[model_id] = updated_model
            self.dirty.add(model_id)
            logger.info(f"Unbanned model {model_id}")
            return True

    async def is_model_banned(self, model_id: str) -> bool:
        """Check if a model is currently banned (status=banned and valid till not passed)."""
        model = self.config.models.get(model_id)
        if not model:
            return False
        if model.status != "BANNED":
            return False
        if model.status_valid_till is None:
            return True
        now = datetime.now(timezone.utc)
        return now < model.status_valid_till

    async def get_judge_config(self) -> JudgeConfig:
        """Return the current judge configuration."""
        return self.config.judge_config

    async def update_judge_config(self, **updates) -> bool:
        """Update judge configuration."""
        async with self.lock:
            config_dict = self.config.judge_config.model_dump()
            for key, value in updates.items():
                if key in config_dict:
                    config_dict[key] = value
                else:
                    logger.warning(f"Ignoring unknown field {key} for judge config")
            new_judge_config = JudgeConfig(**config_dict)
            self.config.judge_config = new_judge_config
            self.dirty.add("__config__")
            logger.debug("Updated judge config")
            return True

    async def get_routing_order_config(self) -> RoutingOrderConfig:
        """Return the current routing order configuration."""
        return self.config.routing_order_config

    async def update_routing_order_config(self, **updates) -> bool:
        """Update routing order configuration."""
        async with self.lock:
            config_dict = self.config.routing_order_config.model_dump()
            for key, value in updates.items():
                if key in config_dict:
                    config_dict[key] = value
                else:
                    logger.warning(f"Ignoring unknown field {key} for routing order config")
            new_routing_order_config = RoutingOrderConfig(**config_dict)
            self.config.routing_order_config = new_routing_order_config
            self.dirty.add("__config__")
            logger.debug("Updated routing order config")
            return True


# Global instance
_state_manager: Optional[StateManager] = None


async def get_state_manager(reload: bool = False) -> StateManager:
    """
    Get or create the global StateManager instance.
    
    Args:
        reload: If True, reload the config from disk even if StateManager exists.
    """
    global _state_manager
    
    if reload and _state_manager is not None:
        # Reload config from disk
        from .config import load_unified_config
        new_config = load_unified_config()
        _state_manager.config = new_config
        logger.debug("StateManager config reloaded from disk")
    
    if _state_manager is None:
        from .config import load_unified_config
        config = load_unified_config()
        _state_manager = StateManager(config)
        _state_manager.start()
        logger.info("StateManager initialized")
    
    return _state_manager


@asynccontextmanager
async def state_manager_context():
    """
    Context manager that ensures the StateManager is properly stopped.
    """
    sm = await get_state_manager()
    try:
        yield sm
    finally:
        await sm.stop()