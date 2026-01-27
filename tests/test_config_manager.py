import json
import threading
from types import SimpleNamespace

import pytest

from sentinelrouter.sentinelrouter import config as config_module
from sentinelrouter.sentinelrouter import config_manager as config_manager_module
from sentinelrouter.sentinelrouter.config_manager import ConfigManager, atomic_write_json


def build_sentinel_config(key_value: str) -> dict:
    return {
        "keys": {
            "deepseek_key": {"type": "deepseek", "value": key_value},
            "anthropic_key": {"type": "anthropic", "value": "sk-anthropic-12345678"},
        },
        "key_instances": {
            "deepseek_primary": {"key_ref": "deepseek_key", "priority": 0, "enabled": True},
            "anthropic_primary": {
                "key_ref": "anthropic_key",
                "priority": 0,
                "enabled": True,
            },
        },
        "models": {
            "deepseek-chat": {
                "enabled": True,
                "provider": "deepseek",
                "model_id": "deepseek-chat",
                "key_instance": "deepseek_primary",
                "pricing": {"input_cost_per_m": 0.1, "output_cost_per_m": 0.2},
                "limits": {
                    "requests_per_minute": 10,
                    "requests_per_day": 100,
                    "tokens_per_minute": 1000,
                },
            },
            "claude-3-opus": {
                "enabled": True,
                "provider": "anthropic",
                "model_id": "claude-3-opus-20240229",
                "key_instance": "anthropic_primary",
                "pricing": {"input_cost_per_m": 1.0, "output_cost_per_m": 2.0},
                "limits": {
                    "requests_per_minute": 5,
                    "requests_per_day": 50,
                    "tokens_per_minute": 500,
                },
            },
        },
        "routing_policy": {
            "weak_tier": {"order": ["deepseek-chat"]},
            "strong_tier": {"order": ["claude-3-opus"]},
        },
        "judge": {
            "enabled": False,
            "model_order": [],
            "complexity_threshold": 0.5,
        },
        "semantic_cache": {
            "enabled": False,
            "min_samples": 3,
            "confidence_threshold": 0.75,
            "ttl_seconds": 3600,
        },
    }


def patch_settings(monkeypatch, sentinel_path: str) -> None:
    dummy_settings = SimpleNamespace(sentinel_config_path=sentinel_path)
    monkeypatch.setattr(config_module, "get_settings", lambda: dummy_settings)
    monkeypatch.setattr(config_manager_module, "get_settings", lambda: dummy_settings)
    monkeypatch.setattr(config_module, "_runtime_config", None)
    monkeypatch.setattr(config_module, "_runtime_config_mtime", None)
    monkeypatch.setattr(config_module, "_runtime_config_source", None)


def test_config_manager_detects_file_changes_and_reload(monkeypatch, tmp_path):
    sentinel_path = tmp_path / "sentinel_config.json"
    data = build_sentinel_config("sk-deepseek-11111111")
    atomic_write_json(str(sentinel_path), data)
    patch_settings(monkeypatch, str(sentinel_path))

    manager = ConfigManager(poll_interval=0.05)
    manager.start()
    try:
        assert manager.wait_for_update(timeout=1.5)
        manager.clear_update_event()

        updated = build_sentinel_config("sk-deepseek-22222222")
        atomic_write_json(str(sentinel_path), updated)

        assert manager.wait_for_update(timeout=2.0)
        current = manager.get_current_config()
        assert current.keys["deepseek_key"].value == "sk-deepseek-22222222"

        runtime_config, _ = config_module.get_runtime_config_with_meta()
        assert runtime_config.keys["deepseek_key"].value == "sk-deepseek-22222222"
    finally:
        manager.stop()


def test_atomic_write_json_prevents_corruption(tmp_path):
    sentinel_path = tmp_path / "sentinel_config.json"
    payloads = [
        build_sentinel_config(f"sk-deepseek-{idx:08d}") for idx in range(6)
    ]

    threads = [
        threading.Thread(target=atomic_write_json, args=(str(sentinel_path), payload))
        for payload in payloads
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    with open(sentinel_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    assert any(data == payload for payload in payloads)
