import json
from types import SimpleNamespace

import pytest

try:
    from fastapi.testclient import TestClient
    FASTAPI_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    FASTAPI_AVAILABLE = False

from sentinelrouter.sentinelrouter import config as config_module
from sentinelrouter.sentinelrouter import config_manager as config_manager_module
if FASTAPI_AVAILABLE:
    from sentinelrouter.sentinelrouter import server as server_module
else:  # pragma: no cover - optional dependency
    server_module = None
from sentinelrouter.sentinelrouter.config_manager import atomic_write_json
from sentinelrouter.sentinelrouter.dashboard import dashboard_home


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


@pytest.fixture()
def admin_client(monkeypatch, tmp_path):
    if not FASTAPI_AVAILABLE:
        pytest.skip("fastapi not installed")
    sentinel_path = tmp_path / "sentinel_config.json"
    atomic_write_json(str(sentinel_path), build_sentinel_config("sk-deepseek-11111111"))

    dummy_settings = SimpleNamespace(
        sentinel_config_path=str(sentinel_path),
        models_config_path=str(tmp_path / "models_config.json"),
        admin_api_token="test-token",
        database_url="sqlite:///:memory:",
        cors_origins="*",
        log_level="INFO",
    )

    monkeypatch.setattr(config_module, "get_settings", lambda: dummy_settings)
    monkeypatch.setattr(config_manager_module, "get_settings", lambda: dummy_settings)
    monkeypatch.setattr(server_module, "get_settings", lambda: dummy_settings)
    monkeypatch.setattr(server_module, "settings", dummy_settings)
    monkeypatch.setattr(config_manager_module, "_config_manager", None)
    monkeypatch.setattr(config_module, "_runtime_config", None)
    monkeypatch.setattr(config_module, "_runtime_config_mtime", None)
    monkeypatch.setattr(config_module, "_runtime_config_source", None)

    with TestClient(server_module.app) as client:
        yield client, sentinel_path


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="fastapi not installed")
def test_admin_keys_rejects_unauthorized(admin_client):
    client, _ = admin_client
    response = client.patch(
        "/admin/config/keys",
        json={"keys": {"deepseek_key": {"value": "sk-deepseek-22222222"}}},
    )
    assert response.status_code == 401


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="fastapi not installed")
def test_admin_keys_validates_format_before_persisting(admin_client):
    client, sentinel_path = admin_client
    response = client.patch(
        "/admin/config/keys",
        headers={"X-Admin-Token": "test-token"},
        json={"keys": {"deepseek_key": {"value": "bad key"}}},
    )
    assert response.status_code == 400

    with open(sentinel_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    assert data["keys"]["deepseek_key"]["value"] == "sk-deepseek-11111111"


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="fastapi not installed")
def test_admin_keys_persists_updates(admin_client):
    client, sentinel_path = admin_client
    response = client.put(
        "/admin/config/keys",
        headers={"X-Admin-Token": "test-token"},
        json={"keys": {"deepseek_key": {"value": "sk-deepseek-33333333"}}},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True

    with open(sentinel_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    assert data["keys"]["deepseek_key"]["value"] == "sk-deepseek-33333333"


def test_dashboard_live_edit_toggle_present():
    import asyncio

    html = asyncio.run(dashboard_home())
    assert "Live Edit" in html
    assert "liveEditToggle" in html
    assert "saveKeysBtn" in html
    assert "toggleLiveEdit" in html


def test_dashboard_toggle_renders_editable_and_readonly_modes():
    import asyncio

    html = asyncio.run(dashboard_home())
    assert "renderApiKeys" in html
    assert "liveEditEnabled" in html
    assert "api-key-input" in html
    assert "api-key-masked" in html


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="fastapi not installed")
def test_admin_keys_update_reflected_in_runtime_config(admin_client):
    client, _ = admin_client
    response = client.patch(
        "/admin/config/keys",
        headers={"X-Admin-Token": "test-token"},
        json={"keys": {"deepseek_key": {"value": "sk-deepseek-44444444"}}},
    )
    assert response.status_code == 200

    runtime_config, _ = config_module.get_runtime_config_with_meta(
        reload_if_changed=False
    )
    assert runtime_config.keys["deepseek_key"].value == "sk-deepseek-44444444"
