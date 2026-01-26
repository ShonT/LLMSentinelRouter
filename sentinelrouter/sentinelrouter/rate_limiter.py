"""
Sliding Window Rate Limiter for LLM API calls.

Tracks requests and tokens per model with accurate time-windowed counting
to enforce requests_per_minute, tokens_per_minute, requests_per_day, and
tokens_per_day limits configured in models_config.json.

Uses collections.deque for efficient O(1) append and O(n) cleanup of expired entries.
"""

import logging
import asyncio
from collections import deque, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Deque, Tuple, Optional

logger = logging.getLogger(__name__)


@dataclass
class RateLimitWindow:
    """Time-windowed tracking for a single model's rate limits."""

    model_id: str

    # Sliding window for requests (timestamp, token_count)
    requests_minute: Deque[Tuple[datetime, int]] = field(default_factory=deque)
    requests_day: Deque[Tuple[datetime, int]] = field(default_factory=deque)

    # Last reset timestamp for daily counters
    last_daily_reset: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # Lock for thread-safe updates
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def _cleanup_expired(
        self, window: Deque[Tuple[datetime, int]], max_age: timedelta
    ) -> None:
        """Remove entries older than max_age from the window."""
        cutoff = datetime.now(timezone.utc) - max_age
        while window and window[0][0] < cutoff:
            window.popleft()

    async def add_request(self, tokens: int = 0) -> None:
        """Record a new request with optional token count."""
        async with self.lock:
            now = datetime.now(timezone.utc)

            # Add to both windows
            self.requests_minute.append((now, tokens))
            self.requests_day.append((now, tokens))

            # Cleanup expired entries (older than 1 minute / 1 day)
            self._cleanup_expired(self.requests_minute, timedelta(minutes=1))
            self._cleanup_expired(self.requests_day, timedelta(days=1))

            logger.debug(
                f"Rate limiter: {self.model_id} added request with {tokens} tokens "
                f"(minute_window={len(self.requests_minute)}, day_window={len(self.requests_day)})"
            )

    async def get_current_usage(self) -> Dict[str, int]:
        """
        Get current usage statistics for this model.

        Returns:
            {
                'requests_last_minute': int,
                'tokens_last_minute': int,
                'requests_last_day': int,
                'tokens_last_day': int
            }
        """
        async with self.lock:
            # Cleanup expired entries first
            self._cleanup_expired(self.requests_minute, timedelta(minutes=1))
            self._cleanup_expired(self.requests_day, timedelta(days=1))

            # Count requests and tokens
            requests_minute = len(self.requests_minute)
            tokens_minute = sum(tokens for _, tokens in self.requests_minute)

            requests_day = len(self.requests_day)
            tokens_day = sum(tokens for _, tokens in self.requests_day)

            return {
                "requests_last_minute": requests_minute,
                "tokens_last_minute": tokens_minute,
                "requests_last_day": requests_day,
                "tokens_last_day": tokens_day,
            }

    async def check_limits(
        self,
        rpm_limit: Optional[int] = None,
        tpm_limit: Optional[int] = None,
        rpd_limit: Optional[int] = None,
        tpd_limit: Optional[int] = None,
        safety_margin: float = 0.95,
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if making another request would exceed any rate limits.

        Args:
            rpm_limit: Requests per minute limit
            tpm_limit: Tokens per minute limit
            rpd_limit: Requests per day limit
            tpd_limit: Tokens per day limit
            safety_margin: Use this fraction of limit (default 0.95 = 95%)

        Returns:
            (allowed, reason) - True if request allowed, False with reason if blocked
        """
        usage = await self.get_current_usage()

        # Apply safety margin to limits
        if rpm_limit and usage["requests_last_minute"] >= int(
            rpm_limit * safety_margin
        ):
            return False, f"RPM limit: {usage['requests_last_minute']}/{rpm_limit}"

        if tpm_limit and usage["tokens_last_minute"] >= int(tpm_limit * safety_margin):
            return False, f"TPM limit: {usage['tokens_last_minute']}/{tpm_limit}"

        if rpd_limit and usage["requests_last_day"] >= int(rpd_limit * safety_margin):
            return False, f"RPD limit: {usage['requests_last_day']}/{rpd_limit}"

        if tpd_limit and usage["tokens_last_day"] >= int(tpd_limit * safety_margin):
            return False, f"TPD limit: {usage['tokens_last_day']}/{tpd_limit}"

        return True, None

    async def reset_daily_counters(self) -> None:
        """Reset daily counters if a day has passed since last reset."""
        async with self.lock:
            now = datetime.now(timezone.utc)
            if now - self.last_daily_reset >= timedelta(days=1):
                # Clear day window
                self.requests_day.clear()
                self.last_daily_reset = now
                logger.info(f"Rate limiter: {self.model_id} daily counters reset")


class RateLimiter:
    """
    Global rate limiter managing all models' rate limits.

    Provides:
    - Accurate time-windowed request/token tracking
    - Preemptive rate limit checking before API calls
    - Automatic daily counter resets
    - Thread-safe concurrent access
    """

    def __init__(self, safety_margin: float = 0.95):
        """
        Initialize rate limiter.

        Args:
            safety_margin: Use this fraction of limits (0.95 = leave 5% buffer)
        """
        self.windows: Dict[str, RateLimitWindow] = defaultdict(
            lambda model_id: RateLimitWindow(model_id=model_id)
        )
        self.safety_margin = safety_margin
        self.reset_task: Optional[asyncio.Task] = None
        self.stop_event = asyncio.Event()
        logger.info(f"RateLimiter initialized with {safety_margin:.0%} safety margin")

    def _get_window(self, model_id: str) -> RateLimitWindow:
        """Get or create rate limit window for a model."""
        if model_id not in self.windows:
            self.windows[model_id] = RateLimitWindow(model_id=model_id)
        return self.windows[model_id]

    async def record_request(self, model_id: str, tokens: int = 0) -> None:
        """
        Record a completed API request for rate limit tracking.

        Args:
            model_id: The model that handled the request
            tokens: Total tokens used (input + output)
        """
        window = self._get_window(model_id)
        await window.add_request(tokens)

    async def check_rate_limits(
        self,
        model_id: str,
        rpm_limit: Optional[int] = None,
        tpm_limit: Optional[int] = None,
        rpd_limit: Optional[int] = None,
        tpd_limit: Optional[int] = None,
        estimated_tokens: int = 0,
    ) -> Tuple[bool, Optional[str], Dict[str, int]]:
        """
        Check if a model can handle another request without exceeding rate limits.

        Args:
            model_id: The model to check
            rpm_limit: Requests per minute limit
            tpm_limit: Tokens per minute limit
            rpd_limit: Requests per day limit
            tpd_limit: Tokens per day limit
            estimated_tokens: Estimated tokens for this request

        Returns:
            (allowed, reason, usage_stats) tuple
            - allowed: True if request can proceed
            - reason: Explanation if blocked, None if allowed
            - usage_stats: Current usage statistics
        """
        window = self._get_window(model_id)
        usage = await window.get_current_usage()

        # Check limits with safety margin
        allowed, reason = await window.check_limits(
            rpm_limit=rpm_limit,
            tpm_limit=tpm_limit,
            rpd_limit=rpd_limit,
            tpd_limit=tpd_limit,
            safety_margin=self.safety_margin,
        )

        # If checking TPM, also verify estimated tokens won't exceed
        if allowed and tpm_limit and estimated_tokens > 0:
            projected_tpm = usage["tokens_last_minute"] + estimated_tokens
            if projected_tpm >= int(tpm_limit * self.safety_margin):
                return False, f"Projected TPM: {projected_tpm}/{tpm_limit}", usage

        return allowed, reason, usage

    async def get_usage_stats(self, model_id: str) -> Dict[str, int]:
        """Get current usage statistics for a model."""
        window = self._get_window(model_id)
        return await window.get_current_usage()

    async def reset_all_daily_counters(self) -> None:
        """Reset daily counters for all models (called at midnight UTC)."""
        for model_id, window in self.windows.items():
            await window.reset_daily_counters()
        logger.info("All daily rate limit counters reset")

    def start(self) -> None:
        """Start background task for daily counter resets."""
        if self.reset_task is None or self.reset_task.done():
            self.reset_task = asyncio.create_task(self._daily_reset_loop())
            logger.info("RateLimiter daily reset task started")

    async def stop(self) -> None:
        """Stop background task."""
        self.stop_event.set()
        if self.reset_task and not self.reset_task.done():
            await self.reset_task
        logger.info("RateLimiter stopped")

    async def _daily_reset_loop(self) -> None:
        """Background loop that resets daily counters at midnight UTC."""
        while not self.stop_event.is_set():
            # Calculate seconds until next midnight UTC
            now = datetime.now(timezone.utc)
            next_midnight = (now + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            seconds_until_midnight = (next_midnight - now).total_seconds()

            logger.debug(
                f"RateLimiter: {seconds_until_midnight:.0f}s until daily reset "
                f"(next reset: {next_midnight.isoformat()})"
            )

            # Sleep until midnight (or until stop event)
            try:
                await asyncio.wait_for(
                    self.stop_event.wait(), timeout=seconds_until_midnight
                )
                # Stop event was set, exit loop
                break
            except asyncio.TimeoutError:
                # Timeout reached (midnight), reset counters
                await self.reset_all_daily_counters()


# Global rate limiter instance
_global_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter(safety_margin: float = 0.95) -> RateLimiter:
    """Get or create the global rate limiter instance."""
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = RateLimiter(safety_margin=safety_margin)
    return _global_rate_limiter
