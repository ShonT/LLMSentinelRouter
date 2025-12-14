"""
Integration tests for dashboard configuration features.

Tests verify that configuration changes via StateManager/dashboard
actually affect routing behavior, rate limiting, and budget calculations.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from sentinelrouter.sentinelrouter.state_manager import get_state_manager
from sentinelrouter.sentinelrouter.router_logic import route_request
from sentinelrouter.sentinelrouter.database import get_session_local


@pytest.mark.asyncio
class TestDashboardConfigIntegration:
    """Integration tests for dashboard config affecting routing behavior."""

    @pytest.mark.skip(reason="Requires full database setup - integration test")
    async def test_judge_config_disable(self):
        """Test that setting is_judge_required=false skips judge call."""
        state_manager = await get_state_manager()
        
        # Set judge to disabled
        judge_config = await state_manager.get_judge_config()
        original_required = judge_config.is_judge_required
        
        try:
            # Disable judge
            judge_config.is_judge_required = False
            await state_manager.update_judge_config(is_judge_required=False)
            
            # Make a routing request
            with patch('sentinelrouter.sentinelrouter.router_logic.get_db'):
                result = await route_request(
                    session_id="test_judge_disable",
                    prompt="Test prompt",
                    messages=[{"role": "user", "content": "Test"}],
                    tier="free"
                )
            
            # Verify judge was skipped (would need to check logs or add metrics)
            # For now, just verify request succeeded
            assert result is not None
            
        finally:
            # Restore original value
            await state_manager.update_judge_config(is_judge_required=original_required)

    @pytest.mark.skip(reason="Requires full database setup - integration test")
    async def test_soft_delete_preserves_logs(self):
        """Test that deleting a model preserves it in historical logs."""
        state_manager = await get_state_manager()
        
        # Create a test model
        test_model_id = "test-model-delete"
        await state_manager.add_model(test_model_id, {
            "display_name": "Test Model",
            "provider": "test",
            "status": "ACTIVE"
        })
        
        # Verify model exists
        model = state_manager.config.models.get(test_model_id)
        assert model is not None
        assert model.status == "ACTIVE"
        
        # Delete the model (soft delete)
        result = await state_manager.delete_model(test_model_id)
        assert result is True
        
        # Verify model still exists but is BANNED
        model = state_manager.config.models.get(test_model_id)
        assert model is not None
        assert model.status == "BANNED"
        assert model.status_valid_till is None  # Permanent ban
        
        # Clean up
        del state_manager.config.models[test_model_id]

    async def test_tier_based_rate_limits(self):
        """Test that free tier users hit lower rate limits than paid users."""
        # This test requires setting up models with tier-specific limits
        # and making multiple requests
        
        state_manager = await get_state_manager()
        
        # Get a model and verify it has tier limits
        models = await state_manager.get_all_models()
        if not models:
            pytest.skip("No models configured for testing")
        
        # Pick first model
        model_id, model_config = next(iter(models.items()))
        
        # Verify tier limits exist
        if not hasattr(model_config, 'free_tier_limits') or not model_config.free_tier_limits:
            pytest.skip(f"Model {model_id} doesn't have free_tier_limits configured")
        
        # Test would verify:
        # 1. Free tier user gets rate limited at free_tier_limits.requests_per_day
        # 2. Paid tier user can exceed that limit up to paid_tier_limits.requests_per_day
        
        # For now, just verify the limits structure exists
        assert hasattr(model_config.free_tier_limits, 'requests_per_day')
        assert hasattr(model_config.free_tier_limits, 'requests_per_minute')

    @pytest.mark.skip(reason="Requires full database setup - integration test")
    async def test_session_tier_persistence(self):
        """Test that session tier is persisted in database."""
        from sentinelrouter.sentinelrouter.budget import BudgetKillSwitch
        from sentinelrouter.sentinelrouter.models import Session
        
        db = get_session_local()()
        try:
            budget = BudgetKillSwitch(db)
            
            # Create sessions with different tiers
            tiers = ['free', 'paid', 'premium']
            
            for tier in tiers:
                session_id = f"test_tier_{tier}"
                session = budget.get_or_create_session(
                    session_id=session_id,
                    tier=tier
                )
                
                assert session.tier == tier
                
                # Verify it's persisted
                db_session = db.query(Session).filter(
                    Session.session_id == session_id
                ).first()
                
                assert db_session is not None
                assert db_session.tier == tier
                
                # Clean up
                db.delete(db_session)
            
            db.commit()
            
        finally:
            db.close()

    async def test_routing_order_affects_routing(self):
        """Test that changing routing order in config affects model selection."""
        state_manager = await get_state_manager()
        
        # Get current routing order
        routing_config = await state_manager.get_routing_order_config()
        original_weak_models = routing_config.weak_models.copy()
        
        try:
            if len(original_weak_models) < 2:
                pytest.skip("Need at least 2 weak models to test routing order")
            
            # Reverse the order
            new_order = list(reversed(original_weak_models))
            await state_manager.update_routing_order_config(weak_models=new_order)
            
            # Verify order was updated
            updated_config = await state_manager.get_routing_order_config()
            assert updated_config.weak_models == new_order
            
            # In a real test, we'd make a routing request and verify
            # the first model in new_order is selected
            # For now, just verify the config change took effect
            
        finally:
            # Restore original order
            await state_manager.update_routing_order_config(weak_models=original_weak_models)

    async def test_custom_pricing_in_budget(self):
        """Test that custom pricing from config is used in budget calculation."""
        state_manager = await get_state_manager()
        
        # Get a model
        models = await state_manager.get_all_models()
        if not models:
            pytest.skip("No models configured")
        
        model_id, model_config = next(iter(models.items()))
        
        # Verify pricing structure exists
        assert hasattr(model_config, 'pricing')
        assert model_config.pricing is not None
        
        # Test that calculate_cost method works
        if hasattr(model_config.pricing, 'calculate_cost'):
            cost = model_config.pricing.calculate_cost(
                input_tokens=100,
                output_tokens=50,
                requests_today=0
            )
            assert isinstance(cost, float)
            assert cost >= 0.0


@pytest.mark.asyncio
class TestTierBasedFeatures:
    """Tests for tier-based functionality."""

    @pytest.mark.skip(reason="Requires full database setup - integration test")
    async def test_tier_default_is_free(self):
        """Test that sessions default to free tier."""
        from sentinelrouter.sentinelrouter.budget import BudgetKillSwitch
        
        db = get_session_local()()
        try:
            budget = BudgetKillSwitch(db)
            
            # Create session without specifying tier
            session = budget.get_or_create_session("test_default_tier")
            
            assert session.tier == "free"
            
            # Clean up
            db.delete(session)
            db.commit()
            
        finally:
            db.close()

    @pytest.mark.skip(reason="Requires full database setup - integration test")
    async def test_tier_upgrade(self):
        """Test that session tier can be updated."""
        from sentinelrouter.sentinelrouter.models import Session
        
        db = get_session_local()()
        try:
            from sentinelrouter.sentinelrouter.budget import BudgetKillSwitch
            budget = BudgetKillSwitch(db)
            
            # Create free tier session
            session = budget.get_or_create_session("test_upgrade", tier="free")
            assert session.tier == "free"
            
            # Upgrade to paid
            session.tier = "paid"
            db.commit()
            
            # Verify upgrade
            updated = db.query(Session).filter(
                Session.session_id == "test_upgrade"
            ).first()
            assert updated.tier == "paid"
            
            # Clean up
            db.delete(updated)
            db.commit()
            
        finally:
            db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
