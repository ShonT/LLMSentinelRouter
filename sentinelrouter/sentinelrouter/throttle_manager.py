"""
Model throttle detection and banning system.

Implements:
- Throttle detection (429 errors, rate limit errors)
- Automatic banning after 2 throttles in 2 minutes
- Extended bans for repeat offenders (2+ bans in 10 min = 10 min ban)
- Thread-safe ban management
"""

import logging
import time
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import Lock

logger = logging.getLogger(__name__)


@dataclass
class ThrottleEvent:
    """Record of a throttle event."""
    timestamp: float
    model_id: str
    error_message: str


@dataclass
class BanRecord:
    """Record of a model ban."""
    model_id: str
    banned_until: float
    ban_count: int = 1
    throttle_events: List[ThrottleEvent] = field(default_factory=list)


class ModelThrottleManager:
    """
    Manages model throttling and automatic bans.
    
    Rules:
    1. 2 throttles in 2 minutes → ban for 2 minutes
    2. 2+ bans in 10 minutes → ban for 10 minutes
    """
    
    def __init__(
        self,
        throttle_window_seconds: int = 120,  # 2 minutes
        throttle_threshold: int = 2,
        short_ban_seconds: int = 120,  # 2 minutes
        extended_ban_window_seconds: int = 600,  # 10 minutes
        extended_ban_threshold: int = 2,
        extended_ban_seconds: int = 600,  # 10 minutes
    ):
        self.throttle_window_seconds = throttle_window_seconds
        self.throttle_threshold = throttle_threshold
        self.short_ban_seconds = short_ban_seconds
        self.extended_ban_window_seconds = extended_ban_window_seconds
        self.extended_ban_threshold = extended_ban_threshold
        self.extended_ban_seconds = extended_ban_seconds
        
        self._throttle_events: Dict[str, List[ThrottleEvent]] = {}
        self._bans: Dict[str, BanRecord] = {}
        self._ban_history: Dict[str, List[float]] = {}  # model_id -> list of ban timestamps
        self._lock = Lock()
        
        logger.info(
            f"ThrottleManager initialized: "
            f"{throttle_threshold} throttles in {throttle_window_seconds}s → {short_ban_seconds}s ban, "
            f"{extended_ban_threshold} bans in {extended_ban_window_seconds}s → {extended_ban_seconds}s ban"
        )
    
    def record_throttle(self, model_id: str, error_message: str) -> Optional[float]:
        """
        Record a throttle event for a model.
        
        Returns:
            Ban duration in seconds if model should be banned, None otherwise.
        """
        with self._lock:
            now = time.time()
            
            # Initialize throttle events list if needed
            if model_id not in self._throttle_events:
                self._throttle_events[model_id] = []
            
            # Add new throttle event
            event = ThrottleEvent(
                timestamp=now,
                model_id=model_id,
                error_message=error_message
            )
            self._throttle_events[model_id].append(event)
            
            # Clean old events (outside window)
            cutoff = now - self.throttle_window_seconds
            self._throttle_events[model_id] = [
                e for e in self._throttle_events[model_id]
                if e.timestamp > cutoff
            ]
            
            # Check if we should ban
            recent_count = len(self._throttle_events[model_id])
            
            if recent_count >= self.throttle_threshold:
                ban_duration = self._apply_ban(model_id, self._throttle_events[model_id])
                logger.warning(
                    f"Model {model_id} banned for {ban_duration}s after {recent_count} throttles"
                )
                return ban_duration
            
            logger.debug(
                f"Throttle recorded for {model_id}: {recent_count}/{self.throttle_threshold} "
                f"in last {self.throttle_window_seconds}s"
            )
            return None
    
    def _apply_ban(self, model_id: str, throttle_events: List[ThrottleEvent]) -> float:
        """Apply a ban to a model. Returns ban duration in seconds."""
        now = time.time()
        
        # Initialize ban history if needed
        if model_id not in self._ban_history:
            self._ban_history[model_id] = []
        
        # Clean old ban history (outside extended window)
        extended_cutoff = now - self.extended_ban_window_seconds
        self._ban_history[model_id] = [
            t for t in self._ban_history[model_id]
            if t > extended_cutoff
        ]
        
        # Check if this is a repeat offender
        recent_bans = len(self._ban_history[model_id])
        
        if recent_bans >= self.extended_ban_threshold:
            # Extended ban for repeat offenders
            ban_duration = self.extended_ban_seconds
            logger.warning(
                f"Applying EXTENDED ban to {model_id}: "
                f"{recent_bans} bans in last {self.extended_ban_window_seconds}s"
            )
        else:
            # Short ban for first offense
            ban_duration = self.short_ban_seconds
            logger.info(
                f"Applying short ban to {model_id}: "
                f"first/second ban, {ban_duration}s timeout"
            )
        
        # Record the ban
        banned_until = now + ban_duration
        self._bans[model_id] = BanRecord(
            model_id=model_id,
            banned_until=banned_until,
            ban_count=recent_bans + 1,
            throttle_events=throttle_events.copy()
        )
        
        # Add to ban history
        self._ban_history[model_id].append(now)
        
        # Clear throttle events for this model
        self._throttle_events[model_id] = []
        
        return ban_duration
    
    def is_banned(self, model_id: str) -> bool:
        """Check if a model is currently banned."""
        with self._lock:
            if model_id not in self._bans:
                return False
            
            ban = self._bans[model_id]
            now = time.time()
            
            if now >= ban.banned_until:
                # Ban expired
                logger.info(f"Ban expired for {model_id}")
                del self._bans[model_id]
                return False
            
            return True
    
    def get_ban_info(self, model_id: str) -> Optional[Dict]:
        """Get information about a model's ban status."""
        with self._lock:
            if model_id not in self._bans:
                return None
            
            ban = self._bans[model_id]
            now = time.time()
            
            if now >= ban.banned_until:
                return None
            
            return {
                "model_id": model_id,
                "banned_until": ban.banned_until,
                "seconds_remaining": int(ban.banned_until - now),
                "ban_count": ban.ban_count,
                "throttle_events_count": len(ban.throttle_events)
            }
    
    def get_all_bans(self) -> List[Dict]:
        """Get information about all active bans."""
        with self._lock:
            now = time.time()
            active_bans = []
            
            for model_id, ban in list(self._bans.items()):
                if now >= ban.banned_until:
                    del self._bans[model_id]
                    continue
                
                active_bans.append({
                    "model_id": model_id,
                    "banned_until": ban.banned_until,
                    "seconds_remaining": int(ban.banned_until - now),
                    "ban_count": ban.ban_count,
                })
            
            return active_bans
    
    def clear_ban(self, model_id: str):
        """Manually clear a ban for a model."""
        with self._lock:
            if model_id in self._bans:
                logger.info(f"Manually clearing ban for {model_id}")
                del self._bans[model_id]
    
    def get_status(self) -> Dict:
        """Get overall status of throttle manager."""
        with self._lock:
            now = time.time()
            
            return {
                "active_bans": len(self._bans),
                "models_with_throttles": len(self._throttle_events),
                "total_throttle_events": sum(len(events) for events in self._throttle_events.values()),
                "bans": self.get_all_bans(),
            }


# Global throttle manager instance
_throttle_manager: Optional[ModelThrottleManager] = None


def get_throttle_manager() -> ModelThrottleManager:
    """Get or create the global throttle manager."""
    global _throttle_manager
    if _throttle_manager is None:
        _throttle_manager = ModelThrottleManager()
    return _throttle_manager
