"""
Module B: Stingy Judge & Categorizer.

Uses the weak model (DeepSeek) to analyze the incoming prompt's complexity.
Outputs a complexity score (0.1-1.0), impact_scope (LOW|MEDIUM|HIGH), and reasoning.
"""

import logging
from typing import Tuple, Dict, Any, Optional
import asyncio
import json

from .clients import get_deepseek_client, LLMResponse
from .config import settings

logger = logging.getLogger(__name__)


class StingyJudge:
    """
    Judge that categorizes request complexity using the weak model.
    """

    def __init__(self):
        self.system_prompt = """You are a Frugality Officer. You hate spending money. Analyze the user's request and output JSON with the following fields:
- "complexity_score": a float between 0.1 (trivial) and 1.0 (extremely complex).
- "impact_scope": one of "LOW", "MEDIUM", or "HIGH". Use these definitions:
    * LOW: Single function, bug fix, documentation.
    * MEDIUM: Class-level change, single-file refactor.
    * HIGH: Multi-file architectural change (impacts >10 files), security critical.
- "reasoning": a brief explanation of your categorization.

Be strict and frugal: default to LOW impact and low complexity unless strongly justified."""

    async def judge(
        self, user_prompt: str, context: Dict[str, Any] = None
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

        try:
            client = await get_deepseek_client()
            response: LLMResponse = await client.chat_completion(
                messages=messages,
                temperature=0.1,
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
            logger.debug(f"Judge result: score={score}, impact={impact}, reasoning={reasoning[:50]}...")
            return score, impact, reasoning
        except Exception as e:
            logger.error(f"Judge failed: {e}. Falling back to default.")
            # Fallback: medium score, LOW impact, generic reasoning
            return 0.5, "LOW", "Judge failed, using default categorization."

    async def judge_batch(self, prompts: list) -> list[Tuple[float, str, str]]:
        """
        Evaluate multiple prompts concurrently.
        """
        tasks = [self.judge(prompt) for prompt in prompts]
        return await asyncio.gather(*tasks, return_exceptions=False)


def complexity_to_route(score: float, threshold: float) -> str:
    """
    Convert a complexity score to a route decision.
    Returns "weak" if score < threshold, else "strong".
    """
    return "weak" if score < threshold else "strong"