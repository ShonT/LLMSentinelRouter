"""
Judge Registry & Backup Judge System

Implements:
- Multiple judge models with priority-based failover
- Circuit breaker pattern for failing judges
- Automatic fallback to backup judges
- Health monitoring for judge models
"""

import logging
import json
import time
from typing import Tuple, Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime, timedelta

from .clients import BaseLLMClient, LLMResponse, LLMClientError
from .metrics import get_metrics_collector

logger = logging.getLogger(__name__)
metrics = get_metrics_collector()


@dataclass
class JudgeHealth:
    """Track health status of a judge model."""
    judge_id: str
    failure_count: int = 0
    last_failure: Optional[datetime] = None
    last_success: Optional[datetime] = None
    circuit_open_until: Optional[datetime] = None
    recent_failures: List[datetime] = None
    
    def __post_init__(self):
        if self.recent_failures is None:
            self.recent_failures = []
    
    def is_circuit_open(self) -> bool:
        """Check if circuit breaker is open."""
        if self.circuit_open_until is None:
            return False
        return datetime.utcnow() < self.circuit_open_until
    
    def get_recent_failure_count(self, window_seconds: int = 300) -> int:
        """Get failure count in recent time window."""
        cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)
        return sum(1 for failure_time in self.recent_failures if failure_time > cutoff)


@dataclass
class JudgeModel:
    """Represents a judge model with its client and configuration."""
    judge_id: str  # e.g., "deepseek-judge-primary", "anthropic-judge-backup"
    client: BaseLLMClient
    priority: int = 0  # 0=primary, 1=first backup, 2=second backup
    display_name: str = ""
    system_prompt: Optional[str] = None  # Custom system prompt for this judge
    temperature: float = 0.1
    
    def __post_init__(self):
        if not self.display_name:
            self.display_name = self.judge_id
        if not self.system_prompt:
            self.system_prompt = self._default_system_prompt()
    
    def _default_system_prompt(self) -> str:
        return """SYSTEM ROLE: Tech Lead & Cost-Minimizer. OBJECTIVE: Route to cheapest model. Bias: UNDERESTIMATE complexity.

SCORING METRIC (0.0 - 1.0):
- 0.0-0.3 (LOW): Syntax, libraries, config, single-function logic, explanations.
- 0.4-0.7 (MEDIUM): Class refactors, unit tests, optimization, standard database/security patterns.
- 0.8-1.0 (HIGH): Cross-service architecture, multi-file migrations, race condition debugging, greenfield system design.

OUTPUT FORMAT (JSON ONLY):
{
  "complexity_score": float,
  "impact_scope": "LOW" | "MEDIUM" | "HIGH",
  "reasoning": "Max 10 words explanation"
}"""
    
    async def judge(
        self,
        user_prompt: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[float, str, str]:
        """
        Evaluate the prompt and return (complexity_score, impact_scope, reasoning).
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"User prompt: {user_prompt}"},
        ]
        if context:
            messages.append({"role": "user", "content": f"Context: {context}"})
        
        response: LLMResponse = await self.client.chat_completion(
            messages=messages,
            temperature=self.temperature,
            response_format={"type": "json_object"},
        )
        
        # Parse JSON from response
        result = json.loads(response.content)
        score = float(result.get("complexity_score", 0.5))
        
        # Clamp to 0.1-1.0
        score = max(0.1, min(1.0, score))
        
        impact = result.get("impact_scope", "LOW").upper()
        if impact not in ("LOW", "MEDIUM", "HIGH"):
            impact = "LOW"
        
        reasoning = result.get("reasoning", "No reasoning provided.")
        
        logger.debug(
            f"Judge {self.judge_id} result: score={score}, "
            f"impact={impact}, reasoning={reasoning[:50]}..."
        )
        
        return score, impact, reasoning


class JudgeHealthTracker:
    """
    Tracks judge health and implements circuit breaker pattern.
    """
    
    def __init__(self, failure_threshold: int = 3, cooldown_seconds: int = 60):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._health: Dict[str, JudgeHealth] = {}
    
    def _get_health(self, judge_id: str) -> JudgeHealth:
        """Get or create health record for judge."""
        if judge_id not in self._health:
            self._health[judge_id] = JudgeHealth(judge_id=judge_id)
        return self._health[judge_id]
    
    def record_failure(self, judge_id: str) -> None:
        """Record a failure for a judge."""
        health = self._get_health(judge_id)
        now = datetime.utcnow()
        
        health.failure_count += 1
        health.last_failure = now
        health.recent_failures.append(now)
        
        # Prune old failures (keep last 1 hour)
        cutoff = now - timedelta(hours=1)
        health.recent_failures = [f for f in health.recent_failures if f > cutoff]
        
        # Open circuit breaker if threshold exceeded
        recent_count = health.get_recent_failure_count(window_seconds=300)
        if recent_count >= self.failure_threshold:
            health.circuit_open_until = now + timedelta(seconds=self.cooldown_seconds)
            logger.warning(
                f"Circuit breaker OPEN for judge {judge_id}: "
                f"{recent_count} failures in last 5 minutes. "
                f"Cooldown until {health.circuit_open_until}"
            )
    
    def record_success(self, judge_id: str) -> None:
        """Record a successful judgment, resetting failure tracking."""
        health = self._get_health(judge_id)
        health.last_success = datetime.utcnow()
        health.failure_count = 0
        health.recent_failures.clear()
        health.circuit_open_until = None
        logger.debug(f"Judge {judge_id} success, circuit reset")
    
    def is_available(self, judge_id: str) -> bool:
        """Check if judge is available (circuit not open)."""
        health = self._get_health(judge_id)
        
        if health.is_circuit_open():
            logger.debug(f"Judge {judge_id} unavailable: circuit breaker open")
            return False
        
        return True
    
    def get_status(self, judge_id: str) -> Dict:
        """Get detailed status for a judge."""
        health = self._get_health(judge_id)
        return {
            "judge_id": judge_id,
            "available": self.is_available(judge_id),
            "circuit_open": health.is_circuit_open(),
            "failure_count": health.failure_count,
            "recent_failures": health.get_recent_failure_count(),
            "last_failure": health.last_failure,
            "last_success": health.last_success,
        }


class JudgeRegistry:
    """
    Central registry for judge models with failover support.
    
    Features:
    - Register multiple judge models with priority
    - Automatic failover when judges fail
    - Circuit breaker to avoid retry storms
    - Health monitoring per judge
    - Fallback to default scoring if all judges fail
    """
    
    def __init__(self, health_tracker: Optional[JudgeHealthTracker] = None):
        self._judges: List[JudgeModel] = []
        self.health_tracker = health_tracker or JudgeHealthTracker()
        # Default to LOW complexity (weak model) when all judges fail
        self._default_fallback = (0.1, "LOW", "All judges failed, assuming weak model (low complexity).")
    
    def register_judge(self, judge: JudgeModel) -> None:
        """Register a judge model."""
        self._judges.append(judge)
        # Sort by priority (0 = highest priority)
        self._judges.sort(key=lambda j: j.priority)
        logger.info(
            f"Registered judge: {judge.judge_id} (priority {judge.priority})"
        )
    
    def get_available_judges(
        self, 
        exclude: Optional[List[str]] = None
    ) -> List[JudgeModel]:
        """
        Get list of available judges, excluding specified ones.
        
        Returns judges in priority order, filtering out:
        - Judges with open circuit breakers
        - Explicitly excluded judges
        """
        exclude = exclude or []
        
        available = [
            j for j in self._judges
            if j.judge_id not in exclude
            and self.health_tracker.is_available(j.judge_id)
        ]
        
        return available
    
    def select_judge(
        self, 
        exclude: Optional[List[str]] = None
    ) -> Optional[JudgeModel]:
        """
        Select the next available judge.
        
        Returns highest priority judge that is:
        - Not in exclude list
        - Has circuit breaker closed
        
        Returns None if no judges available.
        """
        available = self.get_available_judges(exclude)
        
        if not available:
            logger.error(
                f"No available judges! "
                f"Excluded: {exclude}, All: {[j.judge_id for j in self._judges]}"
            )
            return None
        
        selected = available[0]  # Highest priority
        logger.debug(f"Selected judge: {selected.judge_id}")
        return selected
    
    async def judge_with_failover(
        self,
        user_prompt: str,
        context: Optional[Dict[str, Any]] = None,
        max_attempts: int = 3,
    ) -> Tuple[float, str, str, str]:
        """
        Make judgment with automatic failover to backup judges.
        
        Args:
            user_prompt: The prompt to evaluate
            context: Optional context dictionary
            max_attempts: Maximum number of judges to try
        
        Returns:
            Tuple of (complexity_score, impact_scope, reasoning, judge_id used)
        
        If all judges fail, returns default fallback values.
        """
        attempted_judges = []
        last_error = None
        
        for attempt in range(max_attempts):
            judge = self.select_judge(exclude=attempted_judges)
            
            if judge is None:
                break  # No more judges to try
            
            attempted_judges.append(judge.judge_id)
            
            try:
                logger.info(
                    f"Judge attempt {attempt + 1}/{max_attempts}: "
                    f"Using {judge.display_name} ({judge.judge_id})"
                )
                
                # Track latency
                start_time = time.time()
                score, impact, reasoning = await judge.judge(user_prompt, context)
                latency_ms = (time.time() - start_time) * 1000
                
                # Success! Record it and return
                self.health_tracker.record_success(judge.judge_id)
                
                # Record metrics
                metrics.record_judge_latency(judge.judge_id, latency_ms, "success")
                
                # Record fallback if not using primary
                if attempt > 0:
                    primary_judge_id = self._judges[0].judge_id if self._judges else "unknown"
                    metrics.record_fallback("judge", primary_judge_id, judge.judge_id)
                
                logger.info(
                    f"✅ Judge success with {judge.judge_id}: "
                    f"score={score:.3f}, impact={impact}, latency={latency_ms:.0f}ms"
                )
                return score, impact, reasoning, judge.judge_id
                
            except Exception as e:
                last_error = e
                logger.error(
                    f"❌ Judge {judge.judge_id} failed: {e}. "
                    f"Trying next backup..."
                )
                self.health_tracker.record_failure(judge.judge_id)
                
                # Record failed attempt
                metrics.record_judge_latency(judge.judge_id, 0, "error")
                
                # Continue to next judge
                continue
        
        # All judges failed - use default fallback
        logger.error(
            f"All judges failed after {len(attempted_judges)} attempts. "
            f"Tried: {attempted_judges}. Using default fallback."
        )
        
        score, impact, reasoning = self._default_fallback
        return score, impact, f"{reasoning} Error: {last_error}", "fallback"
    
    def get_registry_status(self) -> Dict:
        """Get complete status of all judges."""
        return {
            "judges": [
                {
                    "judge_id": j.judge_id,
                    "display_name": j.display_name,
                    "priority": j.priority,
                    "model": j.client.model_id,
                    **self.health_tracker.get_status(j.judge_id)
                }
                for j in self._judges
            ]
        }
    
    def set_default_fallback(
        self,
        complexity_score: float = 0.1,
        impact_scope: str = "LOW",
        reasoning: str = "All judges failed, assuming weak model (low complexity)."
    ) -> None:
        """Configure the default fallback values when all judges fail."""
        self._default_fallback = (complexity_score, impact_scope, reasoning)
