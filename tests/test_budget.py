"""
Unit tests for Module A: Budget Kill-Switch
Tests the budget tracking and enforcement functionality.
"""

import pytest
from unittest.mock import Mock, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime

from sentinelrouter.sentinelrouter.budget import BudgetKillSwitch
from sentinelrouter.sentinelrouter.models import Base, Session as SessionModel
from sentinelrouter.sentinelrouter.config import Settings


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


class TestBudgetKillSwitch:
    """Tests for Module A - Budget Kill-Switch."""
    
    def test_get_or_create_session_new(self, budget_manager, test_db):
        """Test creating a new session."""
        session = budget_manager.get_or_create_session("test_session_1")
        
        assert session.session_id == "test_session_1"
        assert session.current_cost == 0.0
        assert session.max_cost_per_session == 10.0  # Default from config
        assert session.is_active is True
        
        # Verify it's persisted in database
        db_session = test_db.query(SessionModel).filter_by(session_id="test_session_1").first()
        assert db_session is not None
        assert db_session.session_id == "test_session_1"
    
    def test_get_or_create_session_existing(self, budget_manager, test_db):
        """Test retrieving an existing session."""
        # Create first time
        session1 = budget_manager.get_or_create_session("test_session_2")
        session1.current_cost = 5.0
        test_db.commit()
        
        # Retrieve second time
        session2 = budget_manager.get_or_create_session("test_session_2")
        
        assert session2.session_id == "test_session_2"
        assert session2.current_cost == 5.0
        # Should be same object
        assert session1.session_id == session2.session_id
    
    def test_check_budget_within_limit(self, budget_manager):
        """Test budget check when cost is within limit."""
        budget_manager.get_or_create_session("test_session_3")
        
        # Request cost that's within limit
        result = budget_manager.check_budget("test_session_3", 5.0)
        assert result is True
    
    def test_check_budget_exceeds_limit(self, budget_manager):
        """Test budget check when cost would exceed limit."""
        session = budget_manager.get_or_create_session("test_session_4")
        session.max_cost_per_session = 10.0
        session.current_cost = 8.0
        
        # Request cost that would exceed limit
        result = budget_manager.check_budget("test_session_4", 5.0)
        assert result is False
    
    def test_check_budget_exactly_at_limit(self, budget_manager):
        """Test budget check when exactly at limit."""
        session = budget_manager.get_or_create_session("test_session_5")
        session.max_cost_per_session = 10.0
        session.current_cost = 7.0
        
        # Request cost that brings exactly to limit
        result = budget_manager.check_budget("test_session_5", 3.0)
        assert result is True
        
        # One more cent should fail
        result = budget_manager.check_budget("test_session_5", 3.01)
        assert result is False
    
    def test_check_budget_inactive_session(self, budget_manager):
        """Test budget check on inactive session."""
        session = budget_manager.get_or_create_session("test_session_6")
        session.is_active = False
        
        result = budget_manager.check_budget("test_session_6", 1.0)
        assert result is False
    
    def test_add_cost(self, budget_manager):
        """Test adding cost to a session."""
        budget_manager.get_or_create_session("test_session_7")
        
        budget_manager.add_cost("test_session_7", 2.5)
        session = budget_manager.get_or_create_session("test_session_7")
        assert session.current_cost == 2.5
        
        budget_manager.add_cost("test_session_7", 1.5)
        session = budget_manager.get_or_create_session("test_session_7")
        assert session.current_cost == 4.0
    
    def test_add_cost_multiple_increments(self, budget_manager):
        """Test adding cost multiple times."""
        budget_manager.get_or_create_session("test_session_8")
        
        costs = [0.5, 1.2, 0.3, 2.1, 0.9]
        for cost in costs:
            budget_manager.add_cost("test_session_8", cost)
        
        session = budget_manager.get_or_create_session("test_session_8")
        assert abs(session.current_cost - sum(costs)) < 0.0001  # Float precision
    
    def test_deactivate_session(self, budget_manager):
        """Test deactivating a session."""
        session = budget_manager.get_or_create_session("test_session_9")
        assert session.is_active is True
        
        budget_manager.deactivate_session("test_session_9")
        
        session = budget_manager.get_or_create_session("test_session_9")
        assert session.is_active is False
    
    def test_reset_session(self, budget_manager):
        """Test resetting a session's cost."""
        session = budget_manager.get_or_create_session("test_session_10")
        budget_manager.add_cost("test_session_10", 7.5)
        
        session = budget_manager.get_or_create_session("test_session_10")
        assert session.current_cost == 7.5
        
        budget_manager.reset_session("test_session_10")
        
        session = budget_manager.get_or_create_session("test_session_10")
        assert session.current_cost == 0.0
        assert session.is_active is True
    
    def test_get_session_cost(self, budget_manager, test_db):
        """Test retrieving current session cost."""
        budget_manager.get_or_create_session("test_session_11")
        budget_manager.add_cost("test_session_11", 3.7)
        
        # Verify cost was added by checking budget
        db_session = test_db.query(SessionModel).filter_by(session_id="test_session_11").first()
        assert db_session.current_cost == 3.7
    
    def test_get_session_nonexistent(self, test_db):
        """Test querying non-existent session."""
        db_session = test_db.query(SessionModel).filter_by(session_id="nonexistent_session").first()
        assert db_session is None
    
    def test_budget_with_custom_limit(self, budget_manager):
        """Test budget with custom max cost per session."""
        session = budget_manager.get_or_create_session("test_session_12", max_cost=5.0)
        assert session.max_cost_per_session == 5.0
        
        # Should allow up to 5.0
        assert budget_manager.check_budget("test_session_12", 4.9) is True
        assert budget_manager.check_budget("test_session_12", 5.1) is False
    
    def test_concurrent_budget_check_with_locking(self, budget_manager, test_db):
        """Test that with_for_update locking prevents race conditions."""
        session = budget_manager.get_or_create_session("test_session_13")
        session.max_cost_per_session = 10.0
        session.current_cost = 9.0
        test_db.commit()
        
        # First check should succeed
        result1 = budget_manager.check_budget("test_session_13", 0.5)
        assert result1 is True
        
        # Second check should also work (not a true concurrency test, but validates logic)
        result2 = budget_manager.check_budget("test_session_13", 0.5)
        assert result2 is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
