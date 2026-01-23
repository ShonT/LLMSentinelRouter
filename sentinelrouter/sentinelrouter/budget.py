"""
Module A: Budget Kill‑Switch.

Tracks cumulative cost per session and rejects requests when the session's
MAX_COST_PER_SESSION is exceeded.

Uses optimistic concurrency control (OCC) with version numbers to prevent
race conditions during concurrent budget updates.
"""

import logging
from typing import Optional, Tuple
from datetime import datetime

from sqlalchemy.orm import Session as DBSession

from .models import Session
from .config import get_settings

logger = logging.getLogger(__name__)


class OptimisticLockError(Exception):
    """Raised when an optimistic lock conflict is detected."""
    pass


class BudgetKillSwitch:
    """
    Middleware that enforces per‑session budget limits.
    """

    def __init__(self, db_session: DBSession):
        self.db = db_session

    def get_or_create_session(
        self,
        session_id: str,
        client_ip: Optional[str] = None,
        max_cost: Optional[float] = None,
        tier: Optional[str] = None,
    ) -> Session:
        """
        Retrieve an existing session or create a new one.
        
        Args:
            session_id: Unique session identifier
            client_ip: Client IP address
            max_cost: Maximum cost per session
            tier: Session tier ('free', 'paid', 'premium')
        """
        session = self.db.query(Session).filter(Session.session_id == session_id).first()
        if not session:
            session = Session(
                session_id=session_id,
                client_ip=client_ip,
                tier=tier or "free",  # Default to free tier
                max_cost_per_session=max_cost or get_settings().max_cost_per_session,
                current_cost=0.0,
                is_active=True,
                version=0,  # Initialize version for OCC
            )
            self.db.add(session)
            self.db.commit()
            logger.info(f"Created new session {session_id} with tier={session.tier}, budget={session.max_cost_per_session}")
        return session

    def check_budget(self, session_id: str, cost: float) -> bool:
        """
        Check whether adding `cost` would exceed the session's budget.
        Returns True if allowed, False if budget would be exceeded.
        Uses SELECT FOR UPDATE to prevent race conditions in concurrent scenarios.
        """
        from .models import Session as SessionModel
        # Use row-level locking to prevent race conditions
        session = self.db.query(SessionModel).filter(
            SessionModel.session_id == session_id
        ).with_for_update().first()
        
        if session is None:
            # Session doesn't exist, create it (this is safe as get_or_create handles it)
            session = self.get_or_create_session(session_id)
        
        if not session.is_active:
            logger.warning(f"Session {session_id} is inactive.")
            return False

        new_total = session.current_cost + cost
        if new_total > session.max_cost_per_session:
            logger.warning(
                f"Budget exceeded for session {session_id}: "
                f"current {session.current_cost}, limit {session.max_cost_per_session}, "
                f"attempted +{cost}"
            )
            return False
        return True

    def check_and_reserve_budget(
        self, 
        session_id: str, 
        estimated_cost: float,
        max_retries: int = 3
    ) -> Tuple[bool, Optional[int]]:
        """
        Atomically check and reserve budget using optimistic concurrency control.
        
        This method:
        1. Reads the current session state and version
        2. Checks if estimated_cost would exceed budget
        3. Attempts to reserve the cost atomically with version check
        4. Retries on conflict up to max_retries times
        
        Args:
            session_id: Session identifier
            estimated_cost: Estimated cost to reserve
            max_retries: Maximum retry attempts on conflict
            
        Returns:
            (success, version) - True and version if reserved, False and None if budget exceeded or conflict
        """
        from .models import Session as SessionModel
        
        for attempt in range(max_retries):
            # Read current state without lock (for OCC)
            session = self.db.query(SessionModel).filter(
                SessionModel.session_id == session_id
            ).first()
            
            if session is None:
                session = self.get_or_create_session(session_id)
                self.db.refresh(session)
            
            if not session.is_active:
                logger.warning(f"Session {session_id} is inactive.")
                return False, None
            
            current_version = session.version
            current_cost = session.current_cost
            new_total = current_cost + estimated_cost
            
            if new_total > session.max_cost_per_session:
                logger.warning(
                    f"Budget would be exceeded for session {session_id}: "
                    f"current {current_cost}, limit {session.max_cost_per_session}, "
                    f"attempted +{estimated_cost}"
                )
                return False, None
            
            # Attempt to update with version check (OCC)
            rows_updated = self.db.query(SessionModel).filter(
                SessionModel.session_id == session_id,
                SessionModel.version == current_version
            ).update({
                SessionModel.current_cost: new_total,
                SessionModel.version: current_version + 1
            }, synchronize_session=False)
            
            if rows_updated == 1:
                self.db.commit()
                logger.debug(
                    f"Reserved cost {estimated_cost} for session {session_id}. "
                    f"New total: {new_total}, version: {current_version + 1}"
                )
                return True, current_version + 1
            else:
                # Conflict detected - another transaction modified the row
                self.db.rollback()
                logger.warning(
                    f"OCC conflict for session {session_id} (attempt {attempt + 1}/{max_retries}). "
                    f"Expected version {current_version}, retrying..."
                )
        
        logger.error(f"Failed to reserve budget after {max_retries} attempts for session {session_id}")
        return False, None

    def release_reserved_budget(
        self, 
        session_id: str, 
        reserved_cost: float,
        expected_version: int,
        actual_cost: float
    ) -> bool:
        """
        Adjust reserved budget to actual cost after request completes.
        
        If actual_cost < reserved_cost, refunds the difference.
        If actual_cost > reserved_cost, adds the difference (could fail if exceeds budget).
        
        Args:
            session_id: Session identifier
            reserved_cost: Amount that was reserved
            expected_version: Version when reservation was made
            actual_cost: Actual cost incurred
            
        Returns:
            True if adjustment succeeded, False otherwise
        """
        from .models import Session as SessionModel
        
        cost_difference = actual_cost - reserved_cost
        
        if abs(cost_difference) < 0.0001:
            # No adjustment needed
            return True
        
        session = self.db.query(SessionModel).filter(
            SessionModel.session_id == session_id
        ).first()
        
        if session is None:
            logger.error(f"Session {session_id} not found for budget adjustment")
            return False
        
        new_cost = session.current_cost + cost_difference
        
        # Only check budget limit if we're adding more cost
        if cost_difference > 0 and new_cost > session.max_cost_per_session:
            logger.warning(
                f"Actual cost exceeded reserved amount and budget for session {session_id}. "
                f"Reserved: {reserved_cost}, Actual: {actual_cost}, Limit: {session.max_cost_per_session}"
            )
            # Still update to actual cost (we already performed the operation)
            new_cost = min(new_cost, session.max_cost_per_session * 1.1)  # Allow 10% overage
        
        session.current_cost = new_cost
        session.version += 1
        self.db.commit()
        
        logger.debug(
            f"Adjusted budget for session {session_id}: "
            f"reserved={reserved_cost}, actual={actual_cost}, difference={cost_difference}"
        )
        return True

    def add_cost(self, session_id: str, cost: float) -> None:
        """
        Add cost to the session's cumulative total.
        """
        session = self.get_or_create_session(session_id)
        session.current_cost += cost
        self.db.commit()
        logger.debug(f"Added cost {cost} to session {session_id}. New total: {session.current_cost}")

    def deactivate_session(self, session_id: str) -> None:
        """
        Mark a session as inactive (e.g., after budget exhaustion).
        """
        session = self.get_or_create_session(session_id)
        session.is_active = False
        self.db.commit()
        logger.info(f"Deactivated session {session_id}")

    def reset_session(self, session_id: str, new_max_cost: Optional[float] = None) -> None:
        """
        Reset a session's cumulative cost to zero and optionally update its budget.
        """
        session = self.get_or_create_session(session_id)
        session.current_cost = 0.0
        session.is_active = True
        if new_max_cost is not None:
            session.max_cost_per_session = new_max_cost
        self.db.commit()
        logger.info(f"Reset session {session_id} (cost=0, max={session.max_cost_per_session})")