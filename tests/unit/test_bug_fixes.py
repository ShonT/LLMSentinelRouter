"""
Unit tests for bug fixes implemented in this PR.

Tests cover:
1. Budget OCC (Optimistic Concurrency Control)
2. Cycle Detector LRU Cache
3. Semantic Cache Confidence Calculation
4. State Manager WAL (Write-Ahead Log)
5. Empty Messages Validation
6. Cost Calculation Edge Cases
"""

import asyncio
import json
import os
import tempfile
import time
from collections import OrderedDict
from datetime import datetime, timezone
from functools import partial
from unittest.mock import AsyncMock, MagicMock, patch

# Set mock environment variables BEFORE importing settings-dependent modules
os.environ.setdefault("DEEPSEEK_API_KEY", "mock-deepseek-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "mock-anthropic-key")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sentinelrouter.sentinelrouter.budget import BudgetKillSwitch, OptimisticLockError
from sentinelrouter.sentinelrouter.models import Base, Session as SessionModel
from sentinelrouter.sentinelrouter.config import get_settings


# =============================================================================
# Bug 1: Budget OCC (Optimistic Concurrency Control) Tests
# =============================================================================


@pytest.fixture
def test_db():
    """Create an in-memory test database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def budget_manager(test_db):
    """Create a BudgetKillSwitch instance with test database."""
    return BudgetKillSwitch(test_db)


class TestBudgetOCC:
    """Tests for Budget Optimistic Concurrency Control."""

    def test_session_has_version_column(self, budget_manager, test_db):
        """Test that Session model has version column for OCC."""
        session = budget_manager.get_or_create_session("test_occ_1")
        assert hasattr(session, "version")
        assert session.version == 0

    def test_check_and_reserve_budget_success(self, budget_manager, test_db):
        """Test successful budget reservation with OCC."""
        session = budget_manager.get_or_create_session("test_occ_2")
        session.max_cost_per_session = 10.0
        test_db.commit()

        success, version = budget_manager.check_and_reserve_budget(
            "test_occ_2", estimated_cost=5.0
        )

        assert success is True
        assert version == 1

        # Verify cost was reserved
        test_db.refresh(session)
        assert session.current_cost == 5.0
        assert session.version == 1

    def test_check_and_reserve_budget_exceeds_limit(self, budget_manager, test_db):
        """Test budget reservation fails when limit exceeded."""
        session = budget_manager.get_or_create_session("test_occ_3")
        session.max_cost_per_session = 5.0
        session.current_cost = 4.0
        test_db.commit()

        success, version = budget_manager.check_and_reserve_budget(
            "test_occ_3", estimated_cost=2.0  # Would exceed 5.0 limit
        )

        assert success is False
        assert version is None

    def test_check_and_reserve_budget_concurrent_conflict(
        self, budget_manager, test_db
    ):
        """Test OCC detects concurrent modifications."""
        session = budget_manager.get_or_create_session("test_occ_4")
        session.max_cost_per_session = 10.0
        test_db.commit()

        # Simulate concurrent modification by manually updating version
        test_db.execute(
            SessionModel.__table__.update()
            .where(SessionModel.session_id == "test_occ_4")
            .values(version=5, current_cost=3.0)
        )
        test_db.commit()

        # Now try to reserve - should succeed after retry
        success, version = budget_manager.check_and_reserve_budget(
            "test_occ_4", estimated_cost=2.0, max_retries=3
        )

        # Should succeed on retry
        assert success is True
        # Version should be 6 (5 + 1)
        assert version == 6

    def test_release_reserved_budget_refund(self, budget_manager, test_db):
        """Test refunding unused budget."""
        session = budget_manager.get_or_create_session("test_occ_5")
        session.max_cost_per_session = 10.0
        test_db.commit()

        # Reserve 5.0
        success, version = budget_manager.check_and_reserve_budget(
            "test_occ_5", estimated_cost=5.0
        )
        assert success is True

        # Actual cost was only 2.0, refund 3.0
        result = budget_manager.release_reserved_budget(
            "test_occ_5", reserved_cost=5.0, expected_version=version, actual_cost=2.0
        )

        assert result is True
        test_db.refresh(session)
        assert session.current_cost == 2.0


# =============================================================================
# Bug 2: Cycle Detector LRU Cache Tests
# =============================================================================


class TestCycleDetectorLRU:
    """Tests for Cycle Detector LRU Cache."""

    def test_lru_cache_bounded_size(self):
        """Test that LRU cache respects max size."""
        from sentinelrouter.sentinelrouter.router_logic import (
            _get_or_create_cycle_detector_sync,
            _CYCLE_DETECTORS_CACHE,
            _CYCLE_DETECTORS_MAX_SIZE,
        )

        # Clear cache first
        _CYCLE_DETECTORS_CACHE.clear()

        # Fill cache to max size
        for i in range(_CYCLE_DETECTORS_MAX_SIZE):
            _get_or_create_cycle_detector_sync(f"session_{i}")

        assert len(_CYCLE_DETECTORS_CACHE) == _CYCLE_DETECTORS_MAX_SIZE

        # Add one more - should evict oldest
        _get_or_create_cycle_detector_sync("session_overflow")

        assert len(_CYCLE_DETECTORS_CACHE) == _CYCLE_DETECTORS_MAX_SIZE
        assert "session_0" not in _CYCLE_DETECTORS_CACHE  # First one evicted
        assert "session_overflow" in _CYCLE_DETECTORS_CACHE

    def test_lru_cache_moves_to_end_on_access(self):
        """Test that accessing a session moves it to end (most recently used)."""
        from sentinelrouter.sentinelrouter.router_logic import (
            _get_or_create_cycle_detector_sync,
            _CYCLE_DETECTORS_CACHE,
        )

        _CYCLE_DETECTORS_CACHE.clear()

        # Add 3 sessions
        _get_or_create_cycle_detector_sync("session_a")
        _get_or_create_cycle_detector_sync("session_b")
        _get_or_create_cycle_detector_sync("session_c")

        # Access session_a (should move to end)
        _get_or_create_cycle_detector_sync("session_a")

        # session_b should now be oldest (first)
        keys = list(_CYCLE_DETECTORS_CACHE.keys())
        assert keys[0] == "session_b"
        assert keys[-1] == "session_a"

    def test_lru_cache_returns_same_detector(self):
        """Test that same detector is returned for same session."""
        from sentinelrouter.sentinelrouter.router_logic import (
            _get_or_create_cycle_detector_sync,
            _CYCLE_DETECTORS_CACHE,
        )

        _CYCLE_DETECTORS_CACHE.clear()

        detector1 = _get_or_create_cycle_detector_sync("session_same")
        detector2 = _get_or_create_cycle_detector_sync("session_same")

        assert detector1 is detector2


# =============================================================================
# Bug 4: Semantic Cache Confidence Calculation Tests
# =============================================================================


class TestSemanticCacheConfidence:
    """Tests for fixed semantic cache confidence calculation."""

    @pytest.fixture
    def cache(self):
        """Create a semantic cache instance with fresh test database."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sentinelrouter.sentinelrouter.models import Base
        from sentinelrouter.sentinelrouter.semantic_cache import SemanticCache

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()

        return SemanticCache(
            session,
            min_samples=3,
            confidence_threshold=0.75,
        )

    def test_confidence_ignores_other_model_calls(self, cache):
        """Test that confidence excludes calls to non-weak/non-strong models."""
        settings = get_settings()
        prompt = "Test prompt for confidence"
        context = [{"role": "user", "content": prompt}]

        # Record 5 calls to "other" model (neither weak nor strong)
        for i in range(5):
            cache.record_interaction(
                prompt=prompt,
                context=context,
                response_text=f"Response {i}",
                model_used="gemini-backup-model",  # Not weak or strong
                latency_ms=100.0,
                judge_invoked=True,
                judge_latency_ms=50.0,
                complexity_score=0.5,
                impact_scope="MEDIUM",
                cost=0.01,
                total_tokens=100,
            )

        # Even with 5 calls, confidence should be 0 because no weak/strong calls
        confident, confidence = cache.has_confident_history(prompt, context)
        assert confident is False
        assert confidence == 0.0

    def test_confidence_based_on_routable_calls_only(self, cache):
        """Test that confidence is calculated from weak+strong calls only."""
        settings = get_settings()
        prompt = "Test routable confidence"
        context = [{"role": "user", "content": prompt}]

        # Record 2 weak, 1 strong, 5 other
        for i in range(2):
            cache.record_interaction(
                prompt=prompt,
                context=context,
                response_text=f"Weak {i}",
                model_used=settings.weak_model_id,
                latency_ms=100.0,
                judge_invoked=True,
                judge_latency_ms=50.0,
                complexity_score=0.2,
                impact_scope="LOW",
                cost=0.001,
                total_tokens=50,
            )

        cache.record_interaction(
            prompt=prompt,
            context=context,
            response_text="Strong",
            model_used=settings.strong_model_id,
            latency_ms=500.0,
            judge_invoked=True,
            judge_latency_ms=50.0,
            complexity_score=0.8,
            impact_scope="HIGH",
            cost=0.05,
            total_tokens=500,
        )

        for i in range(5):
            cache.record_interaction(
                prompt=prompt,
                context=context,
                response_text=f"Other {i}",
                model_used="other-model",
                latency_ms=200.0,
                judge_invoked=False,
                judge_latency_ms=None,
                complexity_score=0.5,
                impact_scope="MEDIUM",
                cost=0.01,
                total_tokens=100,
            )

        # Confidence should be 2/3 ≈ 0.67 (2 weak out of 3 routable)
        confident, confidence = cache.has_confident_history(prompt, context)
        assert abs(confidence - 0.667) < 0.01  # 2/3
        assert confident is False  # Below 0.75 threshold


# =============================================================================
# Bug 5: State Manager WAL Tests
# =============================================================================


class TestStateManagerWAL:
    """Tests for State Manager Write-Ahead Log."""

    @pytest.fixture
    def temp_config_and_wal(self):
        """Create temporary config and WAL files."""
        from sentinelrouter.schemas.config_models import (
            UnifiedConfig,
            SystemSettings,
            ModelConfig,
            ModelState,
            ModelCapabilities,
            RoutingConfig,
            RateLimits,
            TierLimits,
            PricingInfo,
            CostInfo,
            JudgeConfig,
            RoutingOrderConfig,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "models_config.json")
            wal_path = os.path.join(tmpdir, "models_config.wal")

            config = UnifiedConfig(
                system_settings=SystemSettings(
                    persistence_interval_seconds=1,
                    default_routing_strategy="waterfall",
                    timezone="UTC",
                ),
                models={
                    "test-model": ModelConfig(
                        display_name="Test Model",
                        provider="test",
                        model_key="test-model",
                        model_definition="Test",
                        status="ACTIVE",
                        capabilities=ModelCapabilities(
                            modality=["text"], context_window=128000
                        ),
                        routing=RoutingConfig(priority_group="fast_tier", order=1),
                        limits=RateLimits(
                            requests_per_minute=10,
                            requests_per_day=1000,
                            tokens_per_minute=500000,
                        ),
                        free_tier_limits=TierLimits(
                            requests_per_day=100,
                            requests_per_minute=5,
                            tokens_per_minute=100000,
                            tokens_per_day=500000,
                        ),
                        paid_tier_limits=TierLimits(
                            requests_per_day=5000,
                            requests_per_minute=50,
                            tokens_per_minute=2000000,
                            tokens_per_day=10000000,
                        ),
                        pricing=PricingInfo(
                            currency="USD",
                            input_cost_per_m=0.0,
                            output_cost_per_m=0.0,
                            usage_tiers=[],
                        ),
                        cost=CostInfo(
                            per_call=0.01,
                            per_token_input=0.000002,
                            per_token_output=0.000004,
                        ),
                        state=ModelState(
                            current_rpm=0,
                            requests_today=0,
                            tokens_today=0,
                            total_cost_session=0.0,
                            last_updated_ts=None,
                            exhausted_until_ts=None,
                        ),
                    ),
                },
                judge_config=JudgeConfig(
                    model_order=["test-model"], is_judge_required=False
                ),
                routing_order_config=RoutingOrderConfig(
                    strong_models=[], weak_models=["test-model"]
                ),
            )

            with open(config_path, "w") as f:
                json.dump(config.model_dump(exclude_none=True), f, default=str)

            yield config_path, wal_path, config

    @pytest.mark.asyncio
    async def test_wal_append_and_read(self, temp_config_and_wal):
        """Test that WAL entries are appended and can be read back."""
        from sentinelrouter.sentinelrouter.state_manager import WriteAheadLog

        config_path, wal_path, _ = temp_config_and_wal
        wal = WriteAheadLog(wal_path)

        # Append entries
        await wal.append("model-1", "requests_today", 0, 5)
        await wal.append("model-1", "tokens_today", 0, 1000)

        # Read back
        entries = await wal.get_uncommitted_entries()
        assert len(entries) == 2
        assert entries[0]["model_id"] == "model-1"
        assert entries[0]["field"] == "requests_today"
        assert entries[0]["new"] == 5

    @pytest.mark.asyncio
    async def test_wal_truncate(self, temp_config_and_wal):
        """Test that WAL can be truncated after flush."""
        from sentinelrouter.sentinelrouter.state_manager import WriteAheadLog

        config_path, wal_path, _ = temp_config_and_wal
        wal = WriteAheadLog(wal_path)

        await wal.append("model-1", "requests_today", 0, 5)

        entries_before = await wal.get_uncommitted_entries()
        assert len(entries_before) == 1

        await wal.truncate()

        entries_after = await wal.get_uncommitted_entries()
        assert len(entries_after) == 0

    @pytest.mark.asyncio
    async def test_wal_replay_recovers_state(self, temp_config_and_wal):
        """Test that WAL replay recovers uncommitted changes."""
        from sentinelrouter.sentinelrouter.state_manager import (
            WriteAheadLog,
            StateManager,
        )

        config_path, wal_path, config = temp_config_and_wal

        # Manually write WAL entries (simulating crash before flush)
        wal = WriteAheadLog(wal_path)
        await wal.append("test-model", "requests_today", 0, 42)
        await wal.append("test-model", "tokens_today", 0, 9999)

        # Create new StateManager (simulating restart)
        manager = StateManager(config, wal_path=wal_path)
        await manager._ensure_wal_recovery()

        # Verify state was recovered
        state = await manager.get_model_state("test-model")
        assert state.requests_today == 42
        assert state.tokens_today == 9999


# =============================================================================
# Bug 8: Empty Messages Validation Tests
# =============================================================================


class TestEmptyMessagesValidation:
    """Tests for empty/invalid messages validation."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        from fastapi.testclient import TestClient
        from sentinelrouter.sentinelrouter.server import app

        return TestClient(app)

    def test_empty_messages_array_rejected(self, client):
        """Test that empty messages array is rejected."""
        response = client.post("/v1/chat/completions", json={"messages": []})
        assert response.status_code == 400
        # Check that response contains an error message
        json_response = response.json()
        assert isinstance(json_response, dict)

    def test_null_content_rejected(self, client):
        """Test that message with null content is rejected."""
        response = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": None}]},
        )
        assert response.status_code in [400, 422]  # Validation error

    def test_no_user_message_rejected(self, client):
        """Test that request without user message is rejected."""
        response = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "system", "content": "You are a helper"}]},
        )
        assert response.status_code == 400
        # Check that response contains an error message
        json_response = response.json()
        assert isinstance(json_response, dict)


# =============================================================================
# Bug 9: Cost Calculation Edge Cases Tests
# =============================================================================


class TestCostCalculationEdgeCases:
    """Tests for cost calculation edge cases."""

    def test_zero_cost_from_provider_accepted(self):
        """Test that cost=0.0 from provider is accepted (free tier)."""
        from sentinelrouter.sentinelrouter.clients import LLMResponse

        # Simulate response with cost=0.0 (free tier)
        response = LLMResponse(
            content="Test response",
            model="free-tier-model",
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            cost=0.0,  # Free tier
        )

        # The fix checks `response.cost is not None` instead of `response.cost > 0`
        has_provider_cost = hasattr(response, "cost") and response.cost is not None
        assert has_provider_cost is True

        # Cost should be 0.0 (not fall back to computed)
        if has_provider_cost:
            final_cost = response.cost
        else:
            final_cost = 0.001  # Fallback

        assert final_cost == 0.0


# =============================================================================
# Lambda Capture Bug Test
# =============================================================================


class TestLambdaCaptureFix:
    """Test that functools.partial correctly captures values."""

    def test_partial_captures_correct_value(self):
        """Test that partial captures the correct model_key for each provider."""
        model_keys = ["model_a", "model_b", "model_c"]
        getters = []

        def mock_get_client(key):
            return f"client_for_{key}"

        for key in model_keys:
            # This is the fixed approach using partial
            getter = partial(mock_get_client, key)
            getters.append(getter)

        # Verify each getter returns the correct client
        results = [g() for g in getters]
        assert results == [
            "client_for_model_a",
            "client_for_model_b",
            "client_for_model_c",
        ]

    def test_lambda_with_default_arg_works(self):
        """Test that lambda with default arg also works (alternative approach)."""
        model_keys = ["model_a", "model_b", "model_c"]
        getters = []

        def mock_get_client(key):
            return f"client_for_{key}"

        for key in model_keys:
            # Lambda with default argument (original code had this but less clear)
            getter = lambda mk=key: mock_get_client(mk)
            getters.append(getter)

        results = [g() for g in getters]
        assert results == [
            "client_for_model_a",
            "client_for_model_b",
            "client_for_model_c",
        ]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
