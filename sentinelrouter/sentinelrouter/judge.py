"""
Module B: Stingy Judge & Categorizer.

Uses judge models (with backup support) to analyze incoming prompt's complexity.
Outputs a complexity score (0.1-1.0), impact_scope (LOW|MEDIUM|HIGH), and reasoning.
Supports multiple judge providers with automatic failover.
"""

import logging
from typing import Tuple, Dict, Any, Optional
import asyncio
import json

from .clients import (
    get_deepseek_client, 
    get_anthropic_client, 
    get_gemini_backup1_client,
    get_gemini_backup2_client,
    LLMResponse
)
from .config import settings
from .judge_registry import JudgeRegistry, JudgeModel, JudgeHealthTracker

logger = logging.getLogger(__name__)

# Global judge registry instance
_JUDGE_REGISTRY: Optional[JudgeRegistry] = None


async def get_judge_registry() -> JudgeRegistry:
    """
    Get or create the global judge registry with configured judges.
    
    Sets up:
    - Primary judge: DeepSeek (priority 0)
    - Backup judge 1: Anthropic Claude Haiku (priority 1)
    - Circuit breaker with 3 failure threshold
    """
    global _JUDGE_REGISTRY
    
    if _JUDGE_REGISTRY is None:
        logger.info("Initializing judge registry with backup support...")
        
        # Create health tracker with circuit breaker
        health_tracker = JudgeHealthTracker(
            failure_threshold=3,  # Open circuit after 3 failures
            cooldown_seconds=60   # 60s cooldown
        )
        
        _JUDGE_REGISTRY = JudgeRegistry(health_tracker=health_tracker)
        
        # Register primary judge: DeepSeek (cheap, fast)
        deepseek_client = await get_deepseek_client()
        primary_judge = JudgeModel(
            judge_id="deepseek-judge-primary",
            client=deepseek_client,
            priority=0,
            display_name="DeepSeek Judge (Primary)",
            temperature=0.1
        )
        _JUDGE_REGISTRY.register_judge(primary_judge)
        
        # Register backup judge 1: Anthropic Claude Haiku
        anthropic_client = await get_anthropic_client()
        backup_judge1 = JudgeModel(
            judge_id="anthropic-judge-backup",
            client=anthropic_client,
            priority=1,
            display_name="Anthropic Judge (Backup 1)",
            temperature=0.1
        )
        _JUDGE_REGISTRY.register_judge(backup_judge1)
        
        # Register backup judge 2: Gemini 2.5 Flash
        gemini1_client = await get_gemini_backup1_client()
        backup_judge2 = JudgeModel(
            judge_id="gemini-judge-backup1",
            client=gemini1_client,
            priority=2,
            display_name="Gemini Flash Judge (Backup 2)",
            temperature=0.1
        )
        _JUDGE_REGISTRY.register_judge(backup_judge2)
        
        # Register backup judge 3: Gemini 2.5 Flash Live
        gemini2_client = await get_gemini_backup2_client()
        backup_judge3 = JudgeModel(
            judge_id="gemini-judge-backup2",
            client=gemini2_client,
            priority=3,
            display_name="Gemini Flash Live Judge (Backup 3)",
            temperature=0.1
        )
        _JUDGE_REGISTRY.register_judge(backup_judge3)
        
        logger.info(
            "✅ Judge registry initialized with 4 judges: "
            f"Primary={primary_judge.judge_id}, "
            f"Backups=[{backup_judge1.judge_id}, {backup_judge2.judge_id}, {backup_judge3.judge_id}]"
        )
    
    return _JUDGE_REGISTRY


class StingyJudge:
    """
    Judge that categorizes request complexity with automatic failover to backup judges.
    
    Features:
    - Primary judge: DeepSeek (cost-effective)
    - Backup judge: Anthropic Claude Haiku (if primary fails)
    - Circuit breaker to prevent retry storms
    - Health monitoring per judge
    """

    def __init__(self):
        self._registry: Optional[JudgeRegistry] = None

    async def _ensure_registry(self):
        """Ensure judge registry is initialized."""
        if self._registry is None:
            self._registry = await get_judge_registry()

    async def judge(
        self, user_prompt: str, context: Dict[str, Any] = None
    ) -> Tuple[float, str, str]:
        """
        Evaluate the prompt and return (complexity_score, impact_scope, reasoning).
        
        Uses judge registry with automatic failover to backup judges if primary fails.
        """
        await self._ensure_registry()
        
        # Use registry with failover
        score, impact, reasoning, judge_id = await self._registry.judge_with_failover(
            user_prompt=user_prompt,
            context=context,
            max_attempts=3  # Try up to 3 judges
        )
        
        logger.info(
            f"Judge result from {judge_id}: "
            f"score={score:.3f}, impact={impact}"
        )
        
        return score, impact, reasoning

    async def judge_batch(self, prompts: list) -> list[Tuple[float, str, str]]:
        """
        Evaluate multiple prompts concurrently.
        """
        tasks = [self.judge(prompt) for prompt in prompts]
        return await asyncio.gather(*tasks, return_exceptions=False)
    
    async def get_status(self) -> Dict:
        """Get status of all judges in the registry."""
        await self._ensure_registry()
        return self._registry.get_registry_status()


def complexity_to_route(score: float, threshold: float) -> str:
    """
    Convert a complexity score to a route decision.
    Returns "weak" if score < threshold, else "strong".
    """
    return "weak" if score < threshold else "strong"