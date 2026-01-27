"""
Configuration manager for SentinelRouter.

Watches the sentinel config (key storage) file for changes and keeps
an in-memory runtime config fresh without requiring a restart.
"""

import json
import logging
import os
import tempfile
import threading
import hashlib
from typing import Dict, Optional, Any

from . import config as config_module
from .config import get_settings
from .config import get_runtime_config_with_meta
from .config import _load_sentinel_config_file, _build_sentinel_config_from_legacy
from .config import get_unified_config
from ..schemas.sentinel_config import SentinelConfig

logger = logging.getLogger(__name__)

ENV_PLACEHOLDER_PATTERN = r"^\$\{[A-Z0-9_]+\}$"


def mask_key_value(value: str) -> str:
    """Mask an API key for display or logging."""
    if not value:
        return "Not set"
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


def validate_key_value(value: str) -> str:
    """Validate API key format and return cleaned value."""
    if not isinstance(value, str):
        raise ValueError("Key value must be a string")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Key value must not be empty")
    if re_search_whitespace(cleaned):
        raise ValueError("Key value must not contain whitespace")
    if len(cleaned) < 8 and not is_env_placeholder(cleaned):
        raise ValueError(
            "Key value must be at least 8 characters or an env placeholder"
        )
    return cleaned


def is_env_placeholder(value: str) -> bool:
    """Return True if the value is an env placeholder like ${API_KEY}."""
    if not isinstance(value, str):
        return False
    return bool(re_fullmatch(ENV_PLACEHOLDER_PATTERN, value))


def re_fullmatch(pattern: str, value: str) -> bool:
    """Local helper to avoid importing re globally in hot paths."""
    import re

    return re.fullmatch(pattern, value) is not None


def re_search_whitespace(value: str) -> bool:
    """Check for whitespace in a string."""
    import re

    return re.search(r"\s", value) is not None


def atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    """
    Atomically write JSON to disk using a temp file + rename.

    This prevents partial writes when concurrent updates occur.
    """
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    file_mode = None
    if os.path.exists(path):
        try:
            file_mode = os.stat(path).st_mode
        except OSError:
            file_mode = None
    fd, temp_path = tempfile.mkstemp(prefix=".tmp-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            json.dump(data, tmp_file, indent=2)
            tmp_file.write("\n")
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        if file_mode is not None:
            os.chmod(temp_path, file_mode)
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def load_raw_sentinel_config(path: str) -> Dict[str, Any]:
    """Load the Sentinel config without resolving env placeholders."""
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def ensure_sentinel_config_file(path: str) -> Dict[str, Any]:
    """
    Ensure sentinel_config.json exists. If missing, build from legacy config.
    """
    if os.path.exists(path):
        return load_raw_sentinel_config(path)
    legacy = get_unified_config()
    sentinel = _build_sentinel_config_from_legacy(legacy)
    data = sentinel.model_dump()
    atomic_write_json(path, data)
    return data


def _file_digest(path: str) -> Optional[str]:
    """Return SHA256 digest for the file contents."""
    try:
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except OSError:
        return None


class ConfigManager:
    """
    Watches the sentinel config file and keeps runtime config in sync.
    """

    def __init__(self, poll_interval: float = 1.0):
        self.poll_interval = poll_interval
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._update_event = threading.Event()
        self._lock = threading.Lock()
        self._current_config: Optional[SentinelConfig] = None
        self._last_mtime: Optional[float] = None
        self._last_digest: Optional[str] = None
        self._last_error: Optional[str] = None

    def start(self) -> None:
        """Start the background watcher thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._watch_loop, name="ConfigManager", daemon=True
        )
        self._thread.start()
        try:
            self.force_reload()
        except Exception as exc:  # pragma: no cover - best effort logging
            logger.warning("ConfigManager initial load failed: %s", exc)

    def stop(self) -> None:
        """Stop the background watcher thread."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self.poll_interval * 2)

    def get_current_config(self) -> Optional[SentinelConfig]:
        """Return the most recently loaded runtime config."""
        with self._lock:
            return self._current_config

    def wait_for_update(self, timeout: Optional[float] = None) -> bool:
        """Block until a config reload is detected."""
        return self._update_event.wait(timeout=timeout)

    def clear_update_event(self) -> None:
        """Clear the update event flag."""
        self._update_event.clear()

    def force_reload(self) -> Optional[SentinelConfig]:
        """Force a reload of the sentinel config regardless of mtime."""
        settings = get_settings()
        sentinel_path = settings.sentinel_config_path
        if not os.path.exists(sentinel_path):
            config, _ = get_runtime_config_with_meta()
            with self._lock:
                self._current_config = config
            return config

        config = _load_sentinel_config_file(sentinel_path)
        mtime = os.path.getmtime(sentinel_path)
        digest = _file_digest(sentinel_path)
        with self._lock:
            self._current_config = config
            self._last_mtime = mtime
            self._last_digest = digest
        config_module._runtime_config = config
        config_module._runtime_config_mtime = mtime
        config_module._runtime_config_source = "sentinel"
        self._update_event.set()
        return config

    def _watch_loop(self) -> None:
        """Poll the sentinel config for changes."""
        while not self._stop_event.wait(self.poll_interval):
            try:
                if self._check_for_changes():
                    self._update_event.set()
            except Exception as exc:
                self._last_error = str(exc)
                logger.warning("ConfigManager reload error: %s", exc)

    def _check_for_changes(self) -> bool:
        settings = get_settings()
        sentinel_path = settings.sentinel_config_path
        if not os.path.exists(sentinel_path):
            config, changed = get_runtime_config_with_meta()
            if changed:
                with self._lock:
                    self._current_config = config
                return True
            return False

        mtime = os.path.getmtime(sentinel_path)
        digest = _file_digest(sentinel_path)
        should_reload = (
            self._last_mtime is None
            or self._last_digest is None
            or mtime != self._last_mtime
            or digest != self._last_digest
        )
        if not should_reload:
            return False

        config = _load_sentinel_config_file(sentinel_path)
        with self._lock:
            self._current_config = config
            self._last_mtime = mtime
            self._last_digest = digest
        config_module._runtime_config = config
        config_module._runtime_config_mtime = mtime
        config_module._runtime_config_source = "sentinel"
        logger.info("Runtime config reloaded from %s", sentinel_path)
        return True


_config_manager: Optional[ConfigManager] = None


def get_config_manager(poll_interval: float = 1.0) -> ConfigManager:
    """Return a singleton ConfigManager."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(poll_interval=poll_interval)
    return _config_manager
