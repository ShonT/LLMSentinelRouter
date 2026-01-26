"""
Semantic hash based request/response cache that records interaction metadata and
computes confidence for reuse decisions.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from .config import get_settings
from .models import SemanticCacheEntry, SemanticCacheStats
from .semantic_hash import compute_simhash, semantic_hash_for_payload

logger = logging.getLogger(__name__)


def _safe_context_string(context: Optional[Any]) -> str:
    """Normalize context into a stable string for hashing."""
    if context is None:
        return ""
    try:
        return json.dumps(context, sort_keys=True)
    except TypeError:
        return str(context)


class SemanticCache:
    """
    Lightweight semantic cache backed by SQLite.

    Responsibilities:
        - Compute semantic hash of prompt+context
        - Record request/response metadata for each hash
        - Maintain aggregated stats (counts, latency mean/variance, token/cost totals)
        - Provide confidence calculations gated by a minimum sample size
        - Evict stale entries based on TTL / max entries
    """

    def __init__(
        self,
        db_session: Session,
        min_samples: Optional[int] = None,
        confidence_threshold: Optional[float] = None,
        ttl_seconds: Optional[int] = None,
        max_entries: Optional[int] = None,
    ):
        self.db = db_session
        self.min_samples = min_samples or get_settings().semantic_cache_min_samples
        self.confidence_threshold = (
            confidence_threshold or get_settings().semantic_cache_confidence_threshold
        )
        self.ttl_seconds = ttl_seconds or get_settings().semantic_cache_ttl_seconds
        self.max_entries = max_entries or get_settings().semantic_cache_max_entries

    # ------------------------------------------------------------------ Hashing
    def build_semantic_hash(self, prompt: str, context: Optional[Any] = None) -> str:
        context_str = _safe_context_string(context)
        simhash_int = semantic_hash_for_payload(prompt, context_str)
        width = max(1, (simhash_int.bit_length() + 3) // 4)
        return f"{simhash_int:0{width}x}"

    def _build_context_hash(self, context: Optional[Any]) -> str:
        context_str = _safe_context_string(context)
        if not context_str:
            return ""
        context_hash = compute_simhash(context_str)
        width = max(1, (context_hash.bit_length() + 3) // 4)
        return f"{context_hash:0{width}x}"

    # ------------------------------------------------------------------ Stats helpers
    def _get_or_create_stats(self, semantic_hash: str) -> SemanticCacheStats:
        stats = self.db.get(SemanticCacheStats, semantic_hash)
        if stats is None:
            stats = SemanticCacheStats(
                semantic_hash=semantic_hash,
                first_seen_at=datetime.utcnow(),
                last_called_at=datetime.utcnow(),
                total_calls=0,
                weak_calls=0,
                strong_calls=0,
                judge_invocations=0,
                total_latency_ms=0.0,
                total_latency_ms_sq=0.0,
                total_cost=0.0,
                total_tokens=0,
            )
            self.db.add(stats)
        return stats

    def _update_stats(
        self,
        stats: SemanticCacheStats,
        model_used: str,
        judge_invoked: bool,
        latency_ms: float,
        cost: float,
        total_tokens: int,
    ) -> None:
        stats.total_calls += 1
        stats.judge_invocations += 1 if judge_invoked else 0
        stats.total_latency_ms += latency_ms
        stats.total_latency_ms_sq += latency_ms * latency_ms
        stats.total_cost += cost
        stats.total_tokens += total_tokens
        stats.last_model = model_used
        stats.last_called_at = datetime.utcnow()

        if model_used == get_settings().weak_model_id:
            stats.weak_calls += 1
        elif model_used == get_settings().strong_model_id:
            stats.strong_calls += 1

    # ------------------------------------------------------------------ Public API
    def record_interaction(
        self,
        prompt: str,
        context: Optional[Any],
        response_text: str,
        model_used: str,
        latency_ms: float,
        judge_invoked: bool,
        judge_latency_ms: Optional[float],
        complexity_score: Optional[float],
        impact_scope: Optional[str],
        cost: float,
        total_tokens: int,
    ) -> SemanticCacheStats:
        semantic_hash = self.build_semantic_hash(prompt, context)
        context_hash = self._build_context_hash(context)
        prompt_preview = prompt[:500] if prompt else None
        response_preview = response_text[:500] if response_text else None

        entry = SemanticCacheEntry(
            semantic_hash=semantic_hash,
            context_hash=context_hash,
            prompt_preview=prompt_preview,
            response_preview=response_preview,
            latency_ms=latency_ms,
            judge_invoked=judge_invoked,
            judge_latency_ms=judge_latency_ms,
            model_used=model_used,
            complexity_score=complexity_score,
            impact_scope=impact_scope,
            cost=cost,
            total_tokens=total_tokens,
        )
        self.db.add(entry)

        stats = self._get_or_create_stats(semantic_hash)
        self._update_stats(
            stats=stats,
            model_used=model_used,
            judge_invoked=judge_invoked,
            latency_ms=latency_ms,
            cost=cost,
            total_tokens=total_tokens,
        )

        self._evict_stale()
        self._enforce_capacity()

        # Flush so callers can inspect updated stats without committing
        self.db.flush()
        return stats

    def get_stats_for_prompt(
        self, prompt: str, context: Optional[Any]
    ) -> Optional[SemanticCacheStats]:
        semantic_hash = self.build_semantic_hash(prompt, context)
        return self.db.get(SemanticCacheStats, semantic_hash)

    def confidence_for_hash(self, semantic_hash: str) -> float:
        """
        Calculate routing confidence based on weak/strong call distribution.

        Confidence is calculated ONLY from weak_calls and strong_calls,
        excluding calls to other models (which don't inform routing decisions).
        This prevents false confidence when using models that aren't classified
        as weak or strong (e.g., backup models, judge models).

        Returns:
            float: Confidence value between 0.0 and 1.0
        """
        stats = self.db.get(SemanticCacheStats, semantic_hash)
        if stats is None or stats.total_calls < self.min_samples:
            return 0.0

        # Only consider weak and strong calls for routing confidence
        routable_calls = stats.weak_calls + stats.strong_calls

        if routable_calls == 0:
            # No routing-relevant calls yet
            return 0.0

        # Calculate confidence as the proportion of the dominant route
        dominant = max(stats.weak_calls, stats.strong_calls)
        confidence = dominant / routable_calls
        return min(1.0, confidence)

    def has_confident_history(
        self, prompt: str, context: Optional[Any]
    ) -> Tuple[bool, float]:
        semantic_hash = self.build_semantic_hash(prompt, context)
        confidence = self.confidence_for_hash(semantic_hash)
        return confidence >= self.confidence_threshold, confidence

    def get_recommended_route(
        self, prompt: str, context: Optional[Any]
    ) -> Optional[str]:
        """
        Get cache-based routing recommendation if confidence threshold is met.

        Returns:
            "weak", "strong", or None if no confident recommendation
        """
        confident, _ = self.has_confident_history(prompt, context)
        if not confident:
            return None

        stats = self.get_stats_for_prompt(prompt, context)
        if not stats:
            return None

        if stats.weak_calls > stats.strong_calls:
            return "weak"
        elif stats.strong_calls > stats.weak_calls:
            return "strong"
        return None

    def summarize_stats(self, semantic_hash: str) -> Optional[Dict[str, Any]]:
        stats = self.db.get(SemanticCacheStats, semantic_hash)
        if stats is None:
            return None

        mean_latency = (
            stats.total_latency_ms / stats.total_calls if stats.total_calls else 0.0
        )
        variance_latency = (
            (stats.total_latency_ms_sq / stats.total_calls) - (mean_latency**2)
            if stats.total_calls
            else 0.0
        )
        # Guard against floating point drift
        variance_latency = max(0.0, variance_latency)

        return {
            "semantic_hash": semantic_hash,
            "total_calls": stats.total_calls,
            "weak_calls": stats.weak_calls,
            "strong_calls": stats.strong_calls,
            "judge_invocations": stats.judge_invocations,
            "mean_latency_ms": mean_latency,
            "latency_variance_ms": variance_latency,
            "total_cost": stats.total_cost,
            "total_tokens": stats.total_tokens,
            "last_model": stats.last_model,
            "last_called_at": stats.last_called_at,
            "first_seen_at": stats.first_seen_at,
            "confidence": self.confidence_for_hash(semantic_hash),
        }

    # ------------------------------------------------------------------ Maintenance
    def _evict_stale(self) -> None:
        if not self.ttl_seconds:
            return
        cutoff = datetime.utcnow() - timedelta(seconds=self.ttl_seconds)
        removed_entries = (
            self.db.query(SemanticCacheEntry)
            .filter(SemanticCacheEntry.created_at < cutoff)
            .delete(synchronize_session=False)
        )
        stale_stats = (
            self.db.query(SemanticCacheStats)
            .filter(SemanticCacheStats.last_called_at < cutoff)
            .all()
        )
        for stat in stale_stats:
            self.db.delete(stat)
        if removed_entries or stale_stats:
            logger.debug(
                "Semantic cache eviction: %s entries, %s stats",
                removed_entries,
                len(stale_stats),
            )

    def _enforce_capacity(self) -> None:
        if not self.max_entries or self.max_entries <= 0:
            return
        total_entries = self.db.query(SemanticCacheEntry).count()
        if total_entries <= self.max_entries:
            return
        # Delete oldest entries beyond capacity
        excess = total_entries - self.max_entries
        oldest_entries = (
            self.db.query(SemanticCacheEntry)
            .order_by(SemanticCacheEntry.created_at.asc())
            .limit(excess)
            .all()
        )
        for entry in oldest_entries:
            self.db.delete(entry)
