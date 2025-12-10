"""
Module C: Dynamic Thresholding (5% Rule).

Adjusts the routing strictness based on the escalation rate (percentage of requests
that are escalated to the strong model). If the escalation rate exceeds the target
(5%), the threshold for using the strong model is raised (making the router “stingier”).
"""

import logging
from typing import List, Optional
from collections import deque
from datetime import datetime, timedelta

from .config import settings

logger = logging.getLogger(__name__)


class DynamicThreshold:
    """
    Maintains a rolling window of routing decisions and adjusts the complexity threshold
    to keep the escalation rate near the target.
    """

    def __init__(
        self,
        target_rate: float = None,
        window_size: int = None,
        initial_threshold: float = None,
    ):
        self.target_rate = target_rate or settings.target_escalation_rate
        self.window_size = window_size or settings.rolling_window_size
        self.threshold = initial_threshold or settings.initial_threshold
        self.decision_window: deque[bool] = deque(maxlen=self.window_size)  # True for strong, False for weak

        logger.info(
            f"DynamicThreshold initialized: target={self.target_rate}, "
            f"window={self.window_size}, initial_threshold={self.threshold}"
        )

    def add_decision(self, used_strong: bool):
        """
        Record a routing decision (True = strong model, False = weak model).
        """
        self.decision_window.append(used_strong)
        logger.debug(f"Added decision: strong={used_strong}. Window size={len(self.decision_window)}")

    def current_escalation_rate(self) -> float:
        """
        Compute the current escalation rate (proportion of strong decisions) over the window.
        Returns 0.0 if window is empty.
        """
        if not self.decision_window:
            return 0.0
        strong_count = sum(1 for d in self.decision_window if d)
        return strong_count / len(self.decision_window)

    def is_strict_mode(self) -> bool:
        """
        Returns True if the current escalation rate exceeds the target rate,
        indicating that we should temporarily require impact_scope == HIGH to escalate.
        """
        if len(self.decision_window) < self.window_size:
            return False
        return self.current_escalation_rate() > self.target_rate

    def adjust_threshold(self) -> Optional[float]:
        """
        Adjust the threshold based on the current escalation rate.
        Returns the new threshold if changed, otherwise None.
        """
        if len(self.decision_window) < self.window_size:
            # Not enough data yet
            return None

        current_rate = self.current_escalation_rate()
        old_threshold = self.threshold

        if current_rate > self.target_rate:
            # Too many escalations: increase threshold (make it harder to go to strong)
            self.threshold = min(0.99, self.threshold + 0.01)
            logger.info(
                f"Rate at {current_rate:.2%}. Tightening belt. New Threshold: {self.threshold:.3f}"
            )
            return self.threshold
        elif current_rate < self.target_rate - 0.02:  # hysteresis
            # Too few escalations: decrease threshold (make it easier to go to strong)
            self.threshold = max(0.0, self.threshold - 0.02)
            logger.info(
                f"Escalation rate {current_rate:.2%} < target {self.target_rate:.2%}. "
                f"Threshold decreased from {old_threshold:.3f} to {self.threshold:.3f}"
            )
            return self.threshold
        else:
            # Within acceptable range
            return None

    def get_threshold(self) -> float:
        """Return the current threshold."""
        return self.threshold

    def reset(self, new_threshold: Optional[float] = None):
        """Reset the decision window and optionally set a new threshold."""
        self.decision_window.clear()
        if new_threshold is not None:
            self.threshold = new_threshold
        logger.info(f"DynamicThreshold reset. Threshold={self.threshold}")