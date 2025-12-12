"""
Module A: Budget Kill‑Switch.

Tracks cumulative cost per session and rejects requests when the session's
MAX_COST_PER_SESSION is exceeded.
"""

import logging
from typing import Optional
from datetime import datetime

from sqlalchemy.orm import Session as DBSession

from .models import Session
from .config import settings

logger = logging.getLogger(__name__)


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
                max_cost_per_session=max_cost or settings.max_cost_per_session,
                current_cost=0.0,
                is_active=True,
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