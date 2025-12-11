"""
Main router logic that integrates all modules (A-D) for intelligent routing.
"""

import asyncio
import logging
import uuid
import time
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

from sqlalchemy.orm import Session as DBSession

from .budget import BudgetKillSwitch
from .judge import StingyJudge, complexity_to_route
from .threshold import DynamicThreshold
from .cycle_detector import CycleDetector
from .clients import (
    get_deepseek_client, 
    get_anthropic_client, 
    get_gemini_backup1_client,
    get_gemini_backup2_client,
    get_gemini_flash_latest_client,
    LLMResponse, 
    LLMClientError
)
from .logging_audit import LoggingAudit
from .config import settings
from .database import get_db
from .models import RoutingDecision
from .metrics import get_metrics_collector
from .throttle_manager import get_throttle_manager

logger = logging.getLogger(__name__)
metrics = get_metrics_collector()
throttle_manager = get_throttle_manager()

# Global cache for cycle detectors (persistent across requests)
# This ensures cycle detection works across multiple API calls
_CYCLE_DETECTORS_CACHE: Dict[str, CycleDetector] = {}


class Router:
    """
    Core router that orchestrates the four modules and makes routing decisions.

    Sequence:
        1. Budget check (Module A)
        2. Cycle detection (Module D) – if loop detected, override to strong model
        3. Judge (Module B) – categorize request (complexity_score, impact_scope, reasoning)
        4. Dynamic thresholding (Module C) – apply threshold and strict mode rules
        5. Route to appropriate model (weak or strong)
        6. Update tracking, logging, and budget
    """

    def __init__(self, db_session: DBSession):
        self.db = db_session
        self.budget = BudgetKillSwitch(db_session)
        self.judge = StingyJudge()
        self.threshold = DynamicThreshold()
        self.audit = LoggingAudit(db_session)
        # Cycle detectors are per session; use global cache to persist across Router instances
        self.cycle_detectors = _CYCLE_DETECTORS_CACHE

    def _get_cycle_detector(self, session_id: str) -> CycleDetector:
        """Get or create a cycle detector for the given session."""
        if session_id not in self.cycle_detectors:
            self.cycle_detectors[session_id] = CycleDetector(session_id)
        return self.cycle_detectors[session_id]

    async def route(
        self,
        session_id: str,
        prompt: str,
        messages: list,
        request_id: Optional[str] = None,
        client_ip: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process a single request through the full routing pipeline.

        Returns a dictionary with:
            - model_used: "deepseek" or "anthropic"
            - response: LLMResponse object
            - complexity_score: float
            - impact_scope: "LOW"|"MEDIUM"|"HIGH"
            - reasoning: str
            - cost: float
            - cycle_detected: bool
            - decision_reason: str
        """
        request_id = request_id or str(uuid.uuid4())
        logger.info(f"Processing request {request_id} for session {session_id}")

        # 1. Budget check (Module A)
        # Estimate worst-case cost (strong model) to check budget.
        estimated_cost = 5.0  # worst-case: Claude Opus $5.00 per million tokens, assume 1M tokens
        if not self.budget.check_budget(session_id, estimated_cost):
            raise ValueError(
                f"Budget exceeded for session {session_id}. "
                f"Current cost: {self.budget.get_or_create_session(session_id).current_cost}, "
                f"limit: {self.budget.get_or_create_session(session_id).max_cost_per_session}"
            )

        # 2. Cycle detection (Module D)
        cycle_detector = self._get_cycle_detector(session_id)
        # Use the last response stored in the detector (if any) to detect cycles with the new prompt
        cycle_detected = cycle_detector.detect_cycle_with_prompt(prompt)
        if cycle_detected:
            logger.warning(f"Cycle detected for session {session_id}. Overriding to strong model.")

        # 3. Judge (Module B)
        try:
            complexity_score, impact_scope, reasoning = await self.judge.judge(prompt)
        except Exception as e:
            logger.error(f"Judge failed: {e}. Falling back to default categorization.")
            complexity_score, impact_scope, reasoning = 0.5, "LOW", "Judge failed, using default."

        logger.info(
            f"Judge: complexity={complexity_score:.3f}, impact={impact_scope}, reasoning={reasoning[:50]}..."
        )

        # 4. Dynamic thresholding (Module C)
        threshold = self.threshold.get_threshold()
        strict_mode = self.threshold.is_strict_mode()
        if strict_mode:
            logger.info(f"Strict mode active (escalation rate > {self.threshold.target_rate:.2%}).")

        # Determine routing decision
        route_decision = self._decide_route(
            complexity_score,
            impact_scope,
            threshold,
            strict_mode,
            cycle_detected,
        )

        decision_reason = self._build_decision_reason(
            route_decision,
            complexity_score,
            impact_scope,
            threshold,
            strict_mode,
            cycle_detected,
        )

        # 5. Select client and make the call with failover support
        response = None
        if route_decision == "weak":
            # Weak model chain: DeepSeek → Gemini 2.5 Flash → Gemini 2.5 Flash Lite → Gemini Flash Latest
            weak_models = [
                ("deepseek", get_deepseek_client),
                ("gemini-2.5-flash", get_gemini_backup1_client),
                ("gemini-2.5-flash-lite", get_gemini_backup2_client),
                ("gemini-flash-latest", get_gemini_flash_latest_client),
            ]
            
            primary_model = weak_models[0][0]
            for idx, (model_name, client_getter) in enumerate(weak_models):
                # Check if model is banned
                if throttle_manager.is_banned(model_name):
                    ban_info = throttle_manager.get_ban_info(model_name)
                    logger.warning(
                        f"Skipping banned weak model {model_name}: "
                        f"{ban_info['seconds_remaining']}s remaining"
                    )
                    continue
                
                try:
                    client = await client_getter()
                    model_used = model_name
                    logger.debug(f"Trying weak model: {model_name}")
                    
                    # Track latency
                    start_time = time.time()
                    response = await client.chat_completion(messages)
                    latency_ms = (time.time() - start_time) * 1000
                    
                    # Record metrics
                    metrics.record_model_latency(model_name, "weak", latency_ms, "success")
                    
                    # Calculate tokens per second
                    if hasattr(response, 'usage') and response.usage:
                        total_tokens = response.usage.get('total_tokens', 0)
                        if total_tokens > 0 and latency_ms > 0:
                            tps = total_tokens / (latency_ms / 1000)
                            metrics.record_tokens_per_second(model_name, "weak", tps, total_tokens)
                    
                    # Record fallback if not using primary
                    if idx > 0:
                        backup_model = weak_models[idx][0]
                        metrics.record_fallback("weak", primary_model, backup_model)
                    
                    break  # Success - exit loop
                except Exception as e:
                    error_msg = str(e).lower()
                    
                    # Check for throttle/rate limit errors
                    is_throttle = any(keyword in error_msg for keyword in [
                        'rate limit', 'throttle', '429', 'quota exceeded', 'too many requests'
                    ])
                    
                    if is_throttle:
                        # Record throttle and potentially ban model
                        ban_duration = throttle_manager.record_throttle(model_name, str(e))
                        if ban_duration:
                            logger.error(
                                f"Model {model_name} BANNED for {ban_duration}s due to throttling"
                            )
                            metrics.record_fallback("weak_throttle_ban", primary_model, model_name)
                    
                    # Record failed attempt
                    metrics.record_model_latency(model_name, "weak", 0, "error")
                    
                    logger.warning(f"Weak model {model_name} failed: {e}")
                    if model_name == weak_models[-1][0]:  # Last model in chain
                        logger.error(f"All weak models failed!")
                        raise LLMClientError(f"All weak models unavailable: {e}")
                    logger.info(f"Falling back to next weak model...")
        else:
            # Strong model chain: Anthropic → Gemini 2.5 Flash
            strong_models = [
                ("anthropic", get_anthropic_client),
                ("gemini-2.5-flash", get_gemini_backup1_client),
            ]
            
            primary_model = strong_models[0][0]
            
            # Log why strong model was selected
            reason_detail = self._build_decision_reason(
                "strong", complexity_score, impact_scope, threshold, strict_mode, cycle_detected
            )
            
            # Get cycle history if cycle was detected
            cycle_history = None
            if cycle_detected and hasattr(cycle_detector, 'recent_hashes'):
                cycle_history = [str(h[0]) for h in list(cycle_detector.recent_hashes)[-5:]]  # Last 5 hashes
            
            logger.info(
                f"🔴 STRONG MODEL SELECTED - Session: {session_id}, "
                f"Reason: {reason_detail}, "
                f"Complexity: {complexity_score:.3f}, "
                f"Impact: {impact_scope}, "
                f"Threshold: {threshold:.3f}, "
                f"Cycle: {cycle_detected}"
            )
            
            for idx, (model_name, client_getter) in enumerate(strong_models):
                # Check if model is banned
                if throttle_manager.is_banned(model_name):
                    ban_info = throttle_manager.get_ban_info(model_name)
                    logger.warning(
                        f"Skipping banned strong model {model_name}: "
                        f"{ban_info['seconds_remaining']}s remaining"
                    )
                    continue
                
                try:
                    client = await client_getter()
                    model_used = model_name
                    logger.debug(f"Trying strong model: {model_name}")
                    
                    # Track latency
                    start_time = time.time()
                    response = await client.chat_completion(messages)
                    latency_ms = (time.time() - start_time) * 1000
                    
                    # Record metrics
                    metrics.record_model_latency(model_name, "strong", latency_ms, "success")
                    
                    # Calculate tokens per second
                    if hasattr(response, 'usage') and response.usage:
                        total_tokens = response.usage.get('total_tokens', 0)
                        if total_tokens > 0 and latency_ms > 0:
                            tps = total_tokens / (latency_ms / 1000)
                            metrics.record_tokens_per_second(model_name, "strong", tps, total_tokens)
                    
                    # Record detailed strong model usage
                    request_text = messages[-1].get('content', '') if messages else prompt
                    response_text = response.content if hasattr(response, 'content') else str(response)
                    
                    metrics.record_strong_model_usage(
                        model_id=model_name,
                        reason=reason_detail,
                        complexity_score=complexity_score,
                        impact_scope=impact_scope,
                        threshold=threshold,
                        cycle_detected=cycle_detected,
                        cycle_history=cycle_history,
                        request_preview=request_text,
                        response_preview=response_text,
                        session_id=session_id
                    )
                    
                    # Record fallback if not using primary
                    if idx > 0:
                        backup_model = strong_models[idx][0]
                        metrics.record_fallback("strong", primary_model, backup_model)
                    
                    break  # Success - exit loop
                except Exception as e:
                    error_msg = str(e).lower()
                    
                    # Check for throttle/rate limit errors
                    is_throttle = any(keyword in error_msg for keyword in [
                        'rate limit', 'throttle', '429', 'quota exceeded', 'too many requests'
                    ])
                    
                    if is_throttle:
                        # Record throttle and potentially ban model
                        ban_duration = throttle_manager.record_throttle(model_name, str(e))
                        if ban_duration:
                            logger.error(
                                f"Model {model_name} BANNED for {ban_duration}s due to throttling"
                            )
                            metrics.record_fallback("strong_throttle_ban", primary_model, model_name)
                    
                    # Record failed attempt
                    metrics.record_model_latency(model_name, "strong", 0, "error")
                    
                    logger.warning(f"Strong model {model_name} failed: {e}")
                    if model_name == strong_models[-1][0]:  # Last model in chain
                        logger.error(f"All strong models failed!")
                        raise LLMClientError(f"All strong models unavailable: {e}")
                    logger.info(f"Falling back to next strong model...")

        # 6. Update cycle detection with the response
        cycle_detector.add_request_response(prompt, response.content)

        # 7. Update budget with actual cost
        self.budget.add_cost(session_id, response.cost)

        # Get current session cost for response headers
        session = self.budget.get_or_create_session(session_id)
        session_cost = session.current_cost

        # 8. Record decision in audit log
        import hashlib
        prompt_hash_int = int(hashlib.sha256(prompt.encode()).hexdigest()[:8], 16)
        response_hash_int = int(hashlib.sha256(response.content.encode()).hexdigest()[:8], 16)
        
        self.audit.log_routing_decision(
            session_id=session_id,
            request_id=request_id,
            model_used=model_used,
            complexity_score=complexity_score,
            cost_incurred=response.cost,
            prompt_hash=prompt_hash_int,
            impact_scope=impact_scope,
            reason=decision_reason,
        )

        # 9. Update dynamic threshold with the decision
        self.threshold.add_decision(route_decision == "strong")
        # Adjust threshold if needed
        new_threshold = self.threshold.adjust_threshold()
        if new_threshold is not None:
            self.audit.log_escalation(
                session_id=session_id,
                escalation_rate=self.threshold.current_escalation_rate(),
                threshold_before=threshold,
                threshold_after=new_threshold,
                reason="automatic adjustment",
            )

        # 10. If cycle detected, log it and record metrics
        if cycle_detected:
            await self.audit.log_cycle_detection(
                session_id=session_id,
                prompt_hash=str(prompt_hash_int),
                response_hash=str(response_hash_int),
            )
            # Record cycle detection metric
            hash_distance = cycle_detector.recent_hashes[-1][0] if cycle_detector.recent_hashes else 0
            metrics.record_cycle_detection(session_id, hash_distance)
            logger.warning(f"Cycle logged for session {session_id}")

        return {
            "model_used": model_used,
            "response": response,
            "complexity_score": complexity_score,
            "impact_scope": impact_scope,
            "reasoning": reasoning,
            "cost": response.cost,
            "session_cost": session_cost,
            "cycle_detected": cycle_detected,
            "decision_reason": decision_reason,
        }

    def _decide_route(
        self,
        complexity_score: float,
        impact_scope: str,
        threshold: float,
        strict_mode: bool,
        cycle_detected: bool,
    ) -> str:
        """
        Determine whether to route to weak or strong model based on all criteria.
        """
        # Cycle detection overrides everything
        if cycle_detected:
            return "strong"

        # Apply strict mode penalty to make escalation harder
        effective_score = complexity_score
        if strict_mode:
            # Add penalty (0.15) to complexity score in strict mode
            # This makes it harder to reach the threshold
            effective_score = complexity_score - 0.15
            logger.debug(f"Strict mode: adjusting complexity from {complexity_score:.3f} to {effective_score:.3f}")

        # Basic threshold rule with effective score
        if effective_score < threshold:
            return "weak"

        # If we are in strict mode, also require HIGH impact to escalate
        if strict_mode and impact_scope != "HIGH":
            logger.debug(f"Strict mode: impact_scope {impact_scope} != HIGH, downgrading to weak.")
            return "weak"

        # Otherwise, strong
        return "strong"

    def _build_decision_reason(
        self,
        route_decision: str,
        complexity_score: float,
        impact_scope: str,
        threshold: float,
        strict_mode: bool,
        cycle_detected: bool,
    ) -> str:
        """Build a human-readable explanation of the routing decision."""
        if cycle_detected:
            return "Cycle detected – forced strong model."

        reason_parts = []
        if complexity_score >= threshold:
            reason_parts.append(f"complexity_score {complexity_score:.3f} >= threshold {threshold:.3f}")
            if strict_mode:
                if impact_scope == "HIGH":
                    reason_parts.append("strict mode but impact_scope is HIGH")
                else:
                    reason_parts.append("strict mode and impact_scope not HIGH -> downgraded")
            else:
                reason_parts.append(f"impact_scope {impact_scope}")
        else:
            reason_parts.append(f"complexity_score {complexity_score:.3f} < threshold {threshold:.3f}")

        return "; ".join(reason_parts)

    async def batch_route(
        self,
        session_id: str,
        prompts: list[str],
        messages_list: list[list],
        client_ip: Optional[str] = None,
    ) -> list[Dict[str, Any]]:
        """
        Process multiple requests concurrently.
        """
        tasks = []
        for prompt, messages in zip(prompts, messages_list):
            task = self.route(
                session_id=session_id,
                prompt=prompt,
                messages=messages,
                client_ip=client_ip,
            )
            tasks.append(task)
        return await asyncio.gather(*tasks, return_exceptions=False)

    def get_session_summary(self, session_id: str) -> Dict[str, Any]:
        """Return a summary of the session's activity."""
        session = self.budget.get_or_create_session(session_id)
        decisions = self.db.query(RoutingDecision).filter_by(session_id=session_id).all()
        total_cost = sum(d.cost_incurred for d in decisions)
        strong_count = sum(1 for d in decisions if d.model_used == "anthropic")
        weak_count = len(decisions) - strong_count
        return {
            "session_id": session_id,
            "current_cost": session.current_cost,
            "max_cost": session.max_cost_per_session,
            "is_active": session.is_active,
            "total_requests": len(decisions),
            "strong_requests": strong_count,
            "weak_requests": weak_count,
            "escalation_rate": strong_count / len(decisions) if decisions else 0.0,
            "current_threshold": self.threshold.get_threshold(),
        }


# Convenience function for using with a database session context
async def route_request(
    session_id: str,
    prompt: str,
    messages: list,
    request_id: Optional[str] = None,
    client_ip: Optional[str] = None,
) -> Dict[str, Any]:
    """
    High-level function that creates a database session and routes a single request.
    """
    with get_db() as db:
        router = Router(db)
        result = await router.route(session_id, prompt, messages, request_id, client_ip)
        return result


# ============================================================================
# Simple test to demonstrate the flow
# ============================================================================

async def _demo_router_flow():
    """
    Demonstrate the router flow using mocked dependencies.

    This function is intended to be run as a simple test to verify that
    the router integrates all modules correctly without making real API calls.
    """
    import sys
    if sys.version_info >= (3, 8):
        from unittest.mock import AsyncMock, patch, MagicMock
    else:
        # Fallback for older Python versions (though we assume 3.8+)
        from unittest.mock import AsyncMock, patch, MagicMock

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from .models import Base

    # 1. Create an in-memory database
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    # 2. Create a router
    router = Router(db)

    # 3. Mock the judge to return a deterministic result
    router.judge.judge = AsyncMock(return_value=(0.8, "HIGH", "Demo reasoning"))

    # 4. Mock the LLM clients
    mock_response = LLMResponse(
        content="This is a mocked response from the LLM.",
        model="mock",
        cost=0.42
    )
    mock_client = AsyncMock()
    mock_client.chat_completion = AsyncMock(return_value=mock_response)

    # Patch the client getters to return our mock client
    with patch('__main__.get_deepseek_client', return_value=mock_client), \
         patch('__main__.get_anthropic_client', return_value=mock_client):
        # 5. Run the router with a simple prompt
        print("=== SentinelRouter Demo Flow ===")
        print("Session: demo-session-001")
        print("Prompt: 'What is the meaning of life?'")
        print()

        result = await router.route(
            session_id="demo-session-001",
            prompt="What is the meaning of life?",
            messages=[{"role": "user", "content": "What is the meaning of life?"}]
        )

        # 6. Print the result
        print("--- Routing Result ---")
        for key, value in result.items():
            if key == 'response':
                print(f"  {key}: {value.content[:60]}...")
            else:
                print(f"  {key}: {value}")
        print()

        # 7. Show session summary
        summary = router.get_session_summary("demo-session-001")
        print("--- Session Summary ---")
        for key, value in summary.items():
            print(f"  {key}: {value}")

        print("\n✅ Demo completed successfully.")
        return result


if __name__ == "__main__":
    # Run the demo when this file is executed directly
    asyncio.run(_demo_router_flow())