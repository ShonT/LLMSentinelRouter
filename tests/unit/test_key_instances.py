import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sentinelrouter.sentinelrouter.model_registry import (
    KeyInstancePool,
    KeyInstanceRecord,
    ProviderHealthTracker,
)
from sentinelrouter.sentinelrouter import clients


def test_key_instance_priority_and_failover():
    health_tracker = ProviderHealthTracker(failure_threshold=1, cooldown_seconds=60)
    pool = KeyInstancePool(health_tracker=health_tracker)

    instances = [
        KeyInstanceRecord(instance_id="primary", api_key="k1", priority=0),
        KeyInstanceRecord(instance_id="backup", api_key="k2", priority=1),
    ]

    ordered = pool.order_instances(instances)
    assert [inst.instance_id for inst in ordered] == ["primary", "backup"]

    pool.record_failure("primary")
    ordered_after_failure = pool.order_instances(instances)
    assert [inst.instance_id for inst in ordered_after_failure] == ["backup"]


@pytest.mark.asyncio
async def test_key_instance_rotation_rebuilds_client():
    clients._key_instance_clients.clear()
    mock_client_primary = MagicMock()
    mock_client_primary.close = AsyncMock()
    mock_client_rotated = MagicMock()
    mock_client_rotated.close = AsyncMock()

    with patch.object(
        clients,
        "_build_client_for_provider",
        side_effect=[mock_client_primary, mock_client_rotated],
    ) as build_client:
        first = await clients.get_client_for_key_instance(
            provider="deepseek",
            model_id="deepseek-chat",
            api_key="key-1",
            key_instance_id="deepseek_primary",
        )
        second = await clients.get_client_for_key_instance(
            provider="deepseek",
            model_id="deepseek-chat",
            api_key="key-1",
            key_instance_id="deepseek_primary",
        )
        rotated = await clients.get_client_for_key_instance(
            provider="deepseek",
            model_id="deepseek-chat",
            api_key="key-2",
            key_instance_id="deepseek_primary",
        )

        assert first is second
        assert rotated is mock_client_rotated
        assert build_client.call_count == 2
        mock_client_primary.close.assert_awaited()
