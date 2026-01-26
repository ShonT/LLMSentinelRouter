"""
Main router logic that integrates all modules (A-D) for intelligent routing.
"""

import asyncio
import logging
import uuid
import time
from collections import OrderedDict
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List

from sqlalchemy.orm import Session as DBSession

from .budget import BudgetKillSwitch
from .judge import StingyJudge, complexity_to_route
from .threshold import DynamicThreshold
from .cycle_detector import CycleDetector
from .clients import get_client_for_key_instance, LLMResponse, LLMClientError
from .logging_audit import LoggingAudit
from .config import get_settings, get_runtime_config_with_meta
from .database import get_db
from .models import RoutingDecision
from .metrics import get_metrics_collector
from .throttle_manager import get_throttle_manager
from .state_manager import get_state_manager
from .semantic_cache import SemanticCache
from .rate_limiter import get_rate_limiter
from .redaction import RedactionEngine, RedactionMode, HMACMasking, SimpleMasking
from .model_registry import KeyInstancePool, KeyInstanceRecord

logger = logging.getLogger(__name__)
metrics = get_metrics_collector()
throttle_manager = get_throttle_manager()
rate_limiter = get_rate_limiter(safety_margin=0.95)

# LRU cache for cycle detectors (persistent across requests, bounded memory)
# Using OrderedDict for O(1) access and O(1) LRU eviction
_CYCLE_DETECTORS_MAX_SIZE = 1000  # Maximum number of sessions to track
_CYCLE_DETECTORS_CACHE: OrderedDict[str, CycleDetector] = OrderedDict()
_CYCLE_DETECTORS_LOCK = asyncio.Lock()


def _get_or_create_cycle_detector_sync(session_id: str) -> CycleDetector:
    """
    Get or create a cycle detector with LRU eviction.
    Thread-safe version for synchronous access.
    """
    global _CYCLE_DETECTORS_CACHE

    if session_id in _CYCLE_DETECTORS_CACHE:
        # Move to end (most recently used)
        _CYCLE_DETECTORS_CACHE.move_to_end(session_id)
        return _CYCLE_DETECTORS_CACHE[session_id]

    # Create new detector
    detector = CycleDetector(session_id)

    # Evict oldest entries if at capacity
    while len(_CYCLE_DETECTORS_CACHE) >= _CYCLE_DETECTORS_MAX_SIZE:
        evicted_session, evicted_detector = _CYCLE_DETECTORS_CACHE.popitem(last=False)
        logger.debug(f"LRU evicted cycle detector for session {evicted_session}")

    _CYCLE_DETECTORS_CACHE[session_id] = detector
    return detector


class Router:
    """
    Core router that orchestrates the four modules and makes routing decisions.

    Sequence:
        1. Budget check (Module A)
        2. Cycle detection (Module D) – if loop detected, override to strong model
        3. Judge (Module B) – categorize request (complexity_score, impact_scope, reasoning)
        4. Dynamic thresholding (Module C) – apply threshold and strict mode rules
        5. Route to appropriate model (weak or strong) using StateManager for limits and state
        6. Update tracking, logging, budget, and model state
    """

    def __init__(self, db_session: DBSession):
        self.db = db_session
        self.budget = BudgetKillSwitch(db_session)
        self.threshold = DynamicThreshold()
        self.audit = LoggingAudit(db_session)
        # Cycle detectors use global LRU cache (no instance reference needed)
        self.state_manager = None  # Will be set async
        self.semantic_cache = SemanticCache(db_session)
        self.judge = None  # Will be initialized with state_manager
        self.redaction_engine = self._init_redaction_engine()
        self.key_instance_pool = KeyInstancePool()

    async def _ensure_state_manager(self):
        if self.state_manager is None:
            self.state_manager = await get_state_manager()
            # Initialize judge with state_manager for config-driven behavior
            if self.judge is None:
                self.judge = StingyJudge(state_manager=self.state_manager)

    def _get_cycle_detector(self, session_id: str) -> CycleDetector:
        """Get or create a cycle detector for the given session using LRU cache."""
        return _get_or_create_cycle_detector_sync(session_id)

    def _init_redaction_engine(self) -> RedactionEngine:
        """Initialize redaction engine from settings."""
        settings = get_settings()

        # Parse mode
        mode_str = settings.redaction_mode.lower()
        mode = (
            RedactionMode(mode_str)
            if mode_str in ["none", "logs", "strict"]
            else RedactionMode.LOGS
        )

        # Parse strategy
        if settings.redaction_strategy.lower() == "hmac":
            strategy = HMACMasking(salt=settings.redaction_salt)
        else:
            strategy = SimpleMasking()

        # Parse categories
        enabled_categories = None
        if settings.redaction_enabled_categories:
            enabled_categories = [
                cat.strip()
                for cat in settings.redaction_enabled_categories.split(",")
                if cat.strip()
            ]

        engine = RedactionEngine(
            mode=mode, masking_strategy=strategy, enabled_categories=enabled_categories
        )

        logger.info(f"Redaction engine initialized: {engine.get_stats()}")
        return engine

    def _get_candidate_models(self, runtime_config, priority_group: str):
        """Return ordered candidate models from the runtime config."""
        if priority_group == "strong_tier":
            order_list = runtime_config.routing_policy.strong_tier.order
        else:
            order_list = runtime_config.routing_policy.weak_tier.order

        candidates = []
        for model_id in order_list:
            model_def = runtime_config.models.get(model_id)
            if model_def and model_def.enabled:
                candidates.append((model_id, model_def))

        if not candidates:
            for model_id, model_def in runtime_config.models.items():
                if model_def.enabled:
                    candidates.append((model_id, model_def))
        return candidates

    def _get_key_instances_for_model(self, runtime_config, model_def):
        """Return key instances ordered by priority for a model."""
        instance_ids = []
        if model_def.key_instances:
            instance_ids = list(model_def.key_instances)
        elif model_def.key_instance:
            instance_ids = [model_def.key_instance]

        if not instance_ids:
            for instance_id, instance in runtime_config.key_instances.items():
                key = runtime_config.keys.get(instance.key_ref)
                if key and key.type == model_def.provider:
                    instance_ids.append(instance_id)

        records = []
        for instance_id in instance_ids:
            instance = runtime_config.key_instances.get(instance_id)
            if not instance or not instance.enabled:
                continue
            key = runtime_config.keys.get(instance.key_ref)
            if not key or not key.value:
                continue
            records.append(
                KeyInstanceRecord(
                    instance_id=instance_id,
                    api_key=key.value,
                    priority=instance.priority,
                    enabled=instance.enabled,
                )
            )

        return self.key_instance_pool.order_instances(records)

    async def route(
        self,
        session_id: str,
        prompt: str,
        messages: list,
        request_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        use_judge: Optional[bool] = None,
        tier: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process a single request through the full routing pipeline.

        Returns a dictionary with:
            - model_used: model identifier (e.g., "deepseek-chat")
            - response: LLMResponse object
            - complexity_score: float
            - impact_scope: "LOW"|"MEDIUM"|"HIGH"
            - reasoning: str
            - cost: float
            - cycle_detected: bool
            - decision_reason: str
        """
        route_start = time.time()
        await self._ensure_state_manager()
        runtime_config, runtime_changed = get_runtime_config_with_meta()
        if runtime_changed:
            self.state_manager = await get_state_manager(reload=True)
        request_id = request_id or str(uuid.uuid4())
        logger.info(f"Processing request {request_id} for session {session_id}")

        # 0. Redaction - Scan for sensitive data and apply based on mode
        redaction_result = self.redaction_engine.scrub(prompt)
        original_prompt = prompt  # Keep original for logs if needed

        # Apply STRICT mode redaction (LLM sees redacted)
        if self.redaction_engine.should_redact_for_llm():
            prompt = redaction_result.redacted_text
            # Also redact messages
            if messages:
                redacted_messages = []
                for msg in messages:
                    redacted_msg = msg.copy()
                    if "content" in redacted_msg:
                        redacted_msg["content"] = self.redaction_engine.scrub(
                            redacted_msg["content"]
                        ).redacted_text
                    redacted_messages.append(redacted_msg)
                messages = redacted_messages

            if redaction_result.has_sensitive_data:
                logger.warning(
                    f"STRICT mode: Redacted sensitive data before LLM processing. "
                    f"Patterns: {redaction_result.patterns_triggered}"
                )

        semantic_hash = self.semantic_cache.build_semantic_hash(prompt, messages)
        cached_stats = self.semantic_cache.get_stats_for_prompt(prompt, messages)
        cache_hit = cached_stats is not None
        cache_confidence = (
            self.semantic_cache.confidence_for_hash(semantic_hash) if cache_hit else 0.0
        )

        # Check if we can use cached routing decision
        cache_based_routing = None
        cache_skip_judge = False
        if cache_hit and cached_stats:
            confident, confidence = self.semantic_cache.has_confident_history(
                prompt, messages
            )
            if confident:
                # Determine preferred model from cache history
                if cached_stats.weak_calls > cached_stats.strong_calls:
                    cache_based_routing = "weak"
                    cache_skip_judge = True
                    logger.info(
                        f"Cache confident history (conf={confidence:.2f}): "
                        f"{cached_stats.weak_calls} weak vs {cached_stats.strong_calls} strong calls - "
                        f"routing to weak model, skipping judge"
                    )
                elif cached_stats.strong_calls > cached_stats.weak_calls:
                    cache_based_routing = "strong"
                    cache_skip_judge = True
                    logger.info(
                        f"Cache confident history (conf={confidence:.2f}): "
                        f"{cached_stats.strong_calls} strong vs {cached_stats.weak_calls} weak calls - "
                        f"routing to strong model, skipping judge"
                    )

        # Record cache lookup with routing decision
        metrics.record_semantic_cache_event(
            "lookup", semantic_hash, cache_hit, cache_confidence, cache_based_routing
        )

        # 1. Budget check (Module A)
        # Estimate worst-case cost (strong model) to check budget.
        estimated_cost = (
            5.0  # worst-case: Claude Opus $5.00 per million tokens, assume 1M tokens
        )
        if not self.budget.check_budget(session_id, estimated_cost):
            raise ValueError(
                f"Budget exceeded for session {session_id}. "
                f"Current cost: {self.budget.get_or_create_session(session_id).current_cost}, "
                f"limit: {self.budget.get_or_create_session(session_id).max_cost_per_session}"
            )

        # 2. Cycle detection (Module D)
        cycle_detector = self._get_cycle_detector(session_id)
        cycle_detected = cycle_detector.detect_cycle_with_prompt(prompt)
        if cycle_detected:
            logger.warning(
                f"Cycle detected for session {session_id}. Overriding to strong model."
            )

        # 3. Judge (Module B) - Conditional based on use_judge parameter and cache
        judge_latency_ms: Optional[float] = None
        judge_skipped = False

        # Determine if we should call judge immediately
        # Priority order:
        # 1. Cache-based routing (if confident history exists)
        # 2. use_judge=True: always call judge
        # 3. use_judge=False: skip judge, assume weak model
        # 4. use_judge=None: conditional mode - skip judge initially, call if weak model takes >15s
        if cache_skip_judge and cache_based_routing:
            # Cache has confident history - skip judge and use cache recommendation
            if cache_based_routing == "weak":
                complexity_score, impact_scope, reasoning = (
                    0.0,
                    "LOW",
                    f"Judge skipped - cache confident (conf={cache_confidence:.2f}) recommends weak model",
                )
            else:
                complexity_score, impact_scope, reasoning = (
                    0.95,
                    "HIGH",
                    f"Judge skipped - cache confident (conf={cache_confidence:.2f}) recommends strong model",
                )
            judge_skipped = True
            metrics.record_judge_skip(
                session_id, f"cache_confident_{cache_based_routing}"
            )
            logger.info(
                f"Judge skipped - using cache-based routing: {cache_based_routing}"
            )
        elif use_judge is False:
            # Skip judge entirely - assume weak model
            complexity_score, impact_scope, reasoning = (
                0.0,
                "LOW",
                "Judge skipped by request (use_judge=false)",
            )
            judge_skipped = True
            metrics.record_judge_skip(session_id, "explicit_skip_use_judge_false")
            logger.info(f"Judge skipped by request - assuming weak model")
        elif use_judge is True:
            # Always call judge
            try:
                judge_start = time.time()
                complexity_score, impact_scope, reasoning = await self.judge.judge(
                    prompt
                )
                judge_latency_ms = (time.time() - judge_start) * 1000
            except Exception as e:
                logger.error(
                    f"Judge failed: {e}. Falling back to default categorization."
                )
                complexity_score, impact_scope, reasoning = (
                    0.5,
                    "LOW",
                    "Judge failed, using default.",
                )

            logger.info(
                f"Judge: complexity={complexity_score:.3f}, impact={impact_scope}, reasoning={reasoning[:50]}..."
            )
        else:
            # Conditional mode (use_judge=None) - skip judge initially, will call if weak model is slow
            complexity_score, impact_scope, reasoning = (
                0.0,
                "LOW",
                "Judge deferred - conditional mode (will call if weak model >15s)",
            )
            judge_skipped = True
            metrics.record_judge_skip(session_id, "conditional_mode_deferred")
            logger.info(
                f"Judge deferred (conditional mode) - will call if weak model takes >15s"
            )

        # 4. Dynamic thresholding (Module C)
        threshold = self.threshold.get_threshold()
        strict_mode = self.threshold.is_strict_mode()
        if strict_mode:
            logger.info(
                f"Strict mode active (escalation rate > {self.threshold.target_rate:.2%})."
            )

        # Determine routing decision
        route_decision = self._decide_route(
            complexity_score,
            impact_scope,
            threshold,
            strict_mode,
            cycle_detected,
        )

        # Store initial route decision for escalation trace
        initial_route_decision = route_decision

        decision_reason = self._build_decision_reason(
            route_decision,
            complexity_score,
            impact_scope,
            threshold,
            strict_mode,
            cycle_detected,
        )

        # Log routing decision
        logger.info(
            f"Routing decision: {route_decision.upper()} tier | "
            f"complexity={complexity_score:.3f}, threshold={threshold:.3f}, "
            f"impact={impact_scope}, strict_mode={strict_mode}, cycle_detected={cycle_detected} | "
            f"Reason: {decision_reason}"
        )

        # 5. Select client and make the call with failover support, using StateManager
        response = None
        model_used = None
        if route_decision == "weak":
            priority_group = "fast_tier"
        else:
            priority_group = "strong_tier"

        candidate_models = self._get_candidate_models(runtime_config, priority_group)

        if not candidate_models:
            raise LLMClientError(f"No active models in priority group {priority_group}")

        # Set tier variable before entering the loop to avoid UnboundLocalError in exception handler
        tier = "weak" if priority_group == "fast_tier" else "strong"

        # Initialize latency and cost tracking variables
        latency_ms = 0.0  # Model API call latency
        final_cost = 0.0
        cost_source = "unknown"
        computed_cost = None

        for model_id, model_def in candidate_models:
            legacy_model_config = await self.state_manager.get_model_config(model_id)
            # Check throttle ban
            if throttle_manager.is_banned(model_id):
                ban_info = throttle_manager.get_ban_info(model_id)
                logger.warning(
                    f"Skipping banned model {model_id}: "
                    f"{ban_info['seconds_remaining']}s remaining"
                )
                continue

            # Check model state exhaustion
            model_state = await self.state_manager.get_model_state(model_id)
            if (
                model_state
                and model_state.exhausted_until_ts
                and model_state.exhausted_until_ts > datetime.utcnow()
            ):
                logger.warning(
                    f"Model {model_id} exhausted until {model_state.exhausted_until_ts}"
                )
                continue

            # Check tier-based rate limits with accurate time-windowed tracking
            active_limits = None
            session_obj = self.budget.get_or_create_session(session_id)
            session_tier = getattr(session_obj, "tier", "free")
            if legacy_model_config and legacy_model_config.limits:
                # Select appropriate limits based on tier
                if session_tier == "free" and legacy_model_config.free_tier_limits:
                    active_limits = legacy_model_config.free_tier_limits
                elif (
                    session_tier in ("paid", "premium")
                    and legacy_model_config.paid_tier_limits
                ):
                    active_limits = legacy_model_config.paid_tier_limits
                else:
                    # Fallback to old limits field
                    active_limits = legacy_model_config.limits
            else:
                active_limits = model_def.limits

            if active_limits:
                # Estimate tokens for this request (rough estimate based on prompt length)
                estimated_tokens = len(prompt.split()) * 2  # ~2 tokens per word average

                # Check rate limits using sliding window rate limiter
                (
                    allowed,
                    limit_reason,
                    usage_stats,
                ) = await rate_limiter.check_rate_limits(
                    model_id=model_id,
                    rpm_limit=active_limits.requests_per_minute
                    if active_limits.requests_per_minute
                    else None,
                    tpm_limit=active_limits.tokens_per_minute
                    if active_limits.tokens_per_minute
                    else None,
                    rpd_limit=active_limits.requests_per_day
                    if active_limits.requests_per_day
                    else None,
                    tpd_limit=getattr(active_limits, "tokens_per_day", None),
                    estimated_tokens=estimated_tokens,
                )

                if not allowed:
                    logger.warning(
                        f"Model {model_id} rate limit check failed for {session_tier} tier: {limit_reason} | "
                        f"Current usage: RPM={usage_stats['requests_last_minute']}/{active_limits.requests_per_minute}, "
                        f"TPM={usage_stats['tokens_last_minute']}/{active_limits.tokens_per_minute}, "
                        f"RPD={usage_stats['requests_last_day']}/{active_limits.requests_per_day}"
                    )
                    # Record metric for preemptive rate limit skip
                    metrics.record_event(
                        "rate_limit_preemptive_skip",
                        {
                            "model_id": model_id,
                            "tier": session_tier,
                            "reason": limit_reason,
                            "usage": usage_stats,
                        },
                    )
                    continue
                else:
                    logger.debug(
                        f"Model {model_id} rate limit check passed | "
                        f"Usage: RPM={usage_stats['requests_last_minute']}/{active_limits.requests_per_minute}, "
                        f"TPM={usage_stats['tokens_last_minute']}/{active_limits.tokens_per_minute}"
                    )

            try:
                key_instances = self._get_key_instances_for_model(
                    runtime_config, model_def
                )
                if not key_instances:
                    raise LLMClientError(
                        f"No enabled key instances for model {model_id}"
                    )

                last_error = None

                for key_instance in key_instances:
                    try:
                        client = await get_client_for_key_instance(
                            provider=model_def.provider.value,
                            model_id=model_def.model_id,
                            api_key=key_instance.api_key,
                            key_instance_id=key_instance.instance_id,
                        )

                        # For OpenRouter/Groq clients, check if API key is configured
                        if (
                            hasattr(client, "is_available")
                            and not client.is_available()
                        ):
                            logger.warning(
                                f"Model {model_id} unavailable (missing API key), "
                                f"skipping key instance {key_instance.instance_id}"
                            )
                            continue

                        model_used = model_id
                        logger.debug(
                            f"Trying model: {model_id} with key instance {key_instance.instance_id}"
                        )

                        # Track latency with timeout check for conditional judge mode
                        start_time = time.time()

                        # In conditional mode, if this is a weak model attempt and judge was skipped,
                        # check if it takes >15s and escalate to judge + strong model if needed
                        if (
                            use_judge is None
                            and judge_skipped
                            and priority_group == "fast_tier"
                        ):
                            # Conditional mode: start weak model call with timeout monitoring
                            try:
                                # Use asyncio.wait_for with 15s timeout
                                response = await asyncio.wait_for(
                                    client.chat_completion(messages), timeout=150.0
                                )
                                latency_ms = (time.time() - start_time) * 1000
                                logger.info(
                                    f"Weak model completed in {latency_ms:.0f}ms (under 15s threshold)"
                                )
                            except asyncio.TimeoutError:
                                # Weak model is taking too long - call judge and potentially escalate
                                logger.warning(
                                    "Weak model exceeded 15s timeout - calling judge for escalation check"
                                )
                                metrics.record_judge_timeout_escalation(
                                    session_id, model_id, 15000
                                )

                                # Call judge now
                                try:
                                    judge_start = time.time()
                                    (
                                        complexity_score,
                                        impact_scope,
                                        reasoning,
                                    ) = await self.judge.judge(prompt)
                                    judge_latency_ms = (
                                        time.time() - judge_start
                                    ) * 1000
                                    judge_skipped = False
                                    logger.info(
                                        f"Post-timeout judge: complexity={complexity_score:.3f}, impact={impact_scope}"
                                    )
                                except Exception as e:
                                    logger.error(
                                        f"Post-timeout judge failed: {e}. Using default."
                                    )
                                    complexity_score, impact_scope, reasoning = (
                                        0.5,
                                        "MEDIUM",
                                        "Post-timeout judge failed",
                                    )

                                # Re-evaluate routing decision
                                threshold = self.threshold.get_threshold()
                                strict_mode = self.threshold.is_strict_mode()
                                new_route_decision = self._decide_route(
                                    complexity_score,
                                    impact_scope,
                                    threshold,
                                    strict_mode,
                                    cycle_detected,
                                )

                                if new_route_decision == "strong":
                                    # Cancel weak model (already timed out) and escalate to strong model
                                    logger.info(
                                        "Escalating to strong model due to timeout + judge recommendation"
                                    )
                                    # Break from weak model loop and restart with strong models
                                    # We'll do this by raising a special exception and catching it
                                    raise TimeoutError(
                                        "Weak model timeout - escalating to strong model"
                                    )
                                else:
                                    # Judge says weak is fine - wait for weak model to complete (no timeout this time)
                                    logger.info(
                                        "Judge says weak model is sufficient - waiting for completion"
                                    )
                                    response = await client.chat_completion(messages)
                                    latency_ms = (time.time() - start_time) * 1000
                        else:
                            # Normal mode: no timeout monitoring
                            response = await client.chat_completion(messages)
                            latency_ms = (time.time() - start_time) * 1000

                        self.key_instance_pool.record_success(key_instance.instance_id)
                        break
                    except LLMClientError as e:
                        last_error = e
                        self.key_instance_pool.record_failure(key_instance.instance_id)
                        logger.warning(
                            f"Key instance {key_instance.instance_id} failed for {model_id}: {e}"
                        )
                        continue

                if response is None:
                    raise LLMClientError(
                        f"All key instances failed for model {model_id}"
                    ) from last_error

                # Record metrics (tier is already set before the loop)
                metrics.record_model_latency(model_id, tier, latency_ms, "success")

                # Calculate cost with priority: provider > computed > unknown
                final_cost = 0.0
                cost_source = "unknown"
                computed_cost = None  # For audit/debug
                input_tokens = 0
                output_tokens = 0
                total_tokens = 0

                # Step 1: Check if provider gave us a cost (including free tier with cost=0)
                # Use `is not None` instead of truthiness to handle cost=0.0 correctly
                if hasattr(response, "cost") and response.cost is not None:
                    final_cost = response.cost
                    cost_source = "provider"
                    # Log if provider returned zero cost (free tier model)
                    if final_cost == 0.0:
                        logger.debug(
                            f"Provider returned zero cost for {model_id} (free tier)"
                        )

                # Step 2: Extract usage for fallback computation and tracking
                if hasattr(response, "usage") and response.usage:
                    input_tokens = response.usage.get("prompt_tokens", 0)
                    output_tokens = response.usage.get("completion_tokens", 0)
                    total_tokens = response.usage.get("total_tokens", 0)

                    # Compute fallback cost if we don't have provider cost
                    if (
                        cost_source == "unknown"
                        and legacy_model_config
                        and legacy_model_config.pricing
                    ):
                        if legacy_model_config.pricing.usage_tiers:
                            # Use tiered pricing
                            current_requests = (
                                model_state.requests_today if model_state else 0
                            )
                            computed_cost = legacy_model_config.pricing.calculate_cost(
                                input_tokens, output_tokens, current_requests
                            )
                        else:
                            # Use flat rate pricing
                            computed_cost = (
                                input_tokens / 1_000_000
                            ) * legacy_model_config.pricing.input_cost_per_m + (
                                output_tokens / 1_000_000
                            ) * legacy_model_config.pricing.output_cost_per_m

                        if computed_cost and computed_cost > 0:
                            final_cost = computed_cost
                            cost_source = "computed"
                    elif cost_source == "unknown" and model_def.pricing:
                        computed_cost = (
                            input_tokens / 1_000_000
                        ) * model_def.pricing.input_cost_per_m + (
                            output_tokens / 1_000_000
                        ) * model_def.pricing.output_cost_per_m
                        if computed_cost and computed_cost > 0:
                            final_cost = computed_cost
                            cost_source = "computed"
                    elif (
                        cost_source == "provider"
                        and legacy_model_config
                        and legacy_model_config.pricing
                    ):
                        # Keep computed_cost for audit even if we're using provider cost
                        if legacy_model_config.pricing.usage_tiers:
                            current_requests = (
                                model_state.requests_today if model_state else 0
                            )
                            computed_cost = legacy_model_config.pricing.calculate_cost(
                                input_tokens, output_tokens, current_requests
                            )
                        else:
                            computed_cost = (
                                input_tokens / 1_000_000
                            ) * legacy_model_config.pricing.input_cost_per_m + (
                                output_tokens / 1_000_000
                            ) * legacy_model_config.pricing.output_cost_per_m

                    # Calculate tokens per second
                    if total_tokens > 0 and latency_ms > 0:
                        tps = total_tokens / (latency_ms / 1000)
                        metrics.record_tokens_per_second(
                            model_id, tier, tps, total_tokens
                        )

                # Update rate limiter with actual tokens used (for accurate time-windowed tracking)
                await rate_limiter.record_request(model_id, total_tokens)

                # Update model state in StateManager (legacy tracking for compatibility)
                await self.state_manager.increment_counter(
                    model_id, "requests_today", 1
                )
                if total_tokens > 0:
                    await self.state_manager.increment_counter(
                        model_id, "tokens_today", total_tokens
                    )
                if final_cost > 0:
                    await self.state_manager.increment_counter(
                        model_id, "total_cost_session", final_cost
                    )

                # Log cost tracking info for debugging
                if (
                    computed_cost is not None
                    and abs(final_cost - computed_cost) > 0.001
                ):
                    logger.debug(
                        f"Cost difference for {model_id}: provider=${final_cost:.6f}, "
                        f"computed=${computed_cost:.6f}, source={cost_source}"
                    )

                # Update timestamp (RPM now tracked by rate_limiter)
                await self.state_manager.update_model_state(
                    model_id, last_updated_ts=datetime.utcnow()
                )

                # Record fallback if not using first candidate
                if candidate_models[0][0] != model_id:
                    primary_model = candidate_models[0][0]
                    metrics.record_fallback(tier, primary_model, model_id)

                break  # Success - exit loop

            except TimeoutError as e:
                # Special handling for timeout-based escalation
                if "Weak model timeout - escalating to strong model" in str(e):
                    logger.info(
                        f"Weak model timeout detected - breaking to escalate to strong tier"
                    )
                    # Break from weak model loop and switch to strong models
                    priority_group = "strong_tier"
                    route_decision = "strong"
                    decision_reason = "Weak model exceeded 15s timeout and judge recommended strong model"

                    # Recalculate candidate models for strong tier
                    candidate_models = self._get_candidate_models(
                        runtime_config, "strong_tier"
                    )

                    if not candidate_models:
                        raise LLMClientError(
                            "No active models in strong_tier after timeout escalation"
                        )

                    # Reset tier for metrics
                    tier = "strong"
                    # Break and restart loop with strong models
                    break
                else:
                    raise
            except Exception as e:
                error_msg = str(e).lower()
                # Check for throttle/rate limit errors
                is_throttle = any(
                    keyword in error_msg
                    for keyword in [
                        "rate limit",
                        "throttle",
                        "429",
                        "quota exceeded",
                        "too many requests",
                    ]
                )
                if is_throttle:
                    # Determine rate limit type from error message
                    limit_type = "unknown"
                    if any(
                        kw in error_msg for kw in ["token", "tpm", "tokens per minute"]
                    ):
                        limit_type = "tokens_per_minute"
                    elif any(
                        kw in error_msg
                        for kw in ["request", "rpm", "requests per minute"]
                    ):
                        limit_type = "requests_per_minute"
                    elif any(kw in error_msg for kw in ["daily", "quota", "day"]):
                        limit_type = "daily_quota"

                    # Get current rate limiter stats for context
                    usage_stats = await rate_limiter.get_usage_stats(model_id)

                    logger.error(
                        f"Model {model_id} hit rate limit (429): {limit_type} | "
                        f"Error: {str(e)} | "
                        f"Current usage: RPM={usage_stats['requests_last_minute']}, "
                        f"TPM={usage_stats['tokens_last_minute']}, "
                        f"RPD={usage_stats['requests_last_day']}, "
                        f"TPD={usage_stats['tokens_last_day']}"
                    )

                    # Record metric for 429 error with type
                    metrics.record_event(
                        "rate_limit_429_error",
                        {
                            "model_id": model_id,
                            "limit_type": limit_type,
                            "usage": usage_stats,
                        },
                    )

                    ban_duration = throttle_manager.record_throttle(model_id, str(e))
                    if ban_duration:
                        logger.error(
                            f"Model {model_id} BANNED for {ban_duration}s due to throttling"
                        )
                        metrics.record_fallback(
                            f"{tier}_throttle_ban", candidate_models[0][0], model_id
                        )

                # Record failed attempt
                metrics.record_model_latency(model_id, tier, 0, "error")
                logger.warning(f"Model {model_id} failed: {e}")
                if model_id == candidate_models[-1][0]:
                    logger.error(f"All models in {priority_group} failed!")
                    raise LLMClientError(
                        f"All models in {priority_group} unavailable: {e}"
                    )
                logger.info(f"Falling back to next model in {priority_group}...")

        if response is None or model_used is None:
            raise LLMClientError("No model could be selected for the request.")

        # 6. Update cycle detection with the response
        # IMPORTANT: Only update cycle detection after successful completion
        # to avoid false positives when requests fail and are retried
        if response and hasattr(response, "content") and response.content:
            cycle_detector.add_request_response(prompt, response.content)
            logger.debug(
                f"Updated cycle detector with successful response for session {session_id}"
            )
        else:
            logger.warning(
                f"Skipping cycle detector update - no valid response content for session {session_id}"
            )
            # Clear last response to prevent stale data from affecting future cycle detection
            cycle_detector.clear_last_response()

        # 7. Update budget with actual cost
        self.budget.add_cost(session_id, final_cost)

        # Get current session cost for response headers
        session = self.budget.get_or_create_session(session_id)
        session_cost = session.current_cost

        # 8. Record decision in audit log
        import hashlib

        prompt_hash_int = int(hashlib.sha256(prompt.encode()).hexdigest()[:8], 16)
        response_hash_int = int(
            hashlib.sha256(response.content.encode()).hexdigest()[:8], 16
        )

        # Apply LOGS mode redaction (audit logs see redacted, LLM saw original)
        log_prompt = prompt
        log_messages = messages
        log_response_content = response.content

        if (
            self.redaction_engine.should_redact_for_logs()
            and not self.redaction_engine.should_redact_for_llm()
        ):
            # LOGS mode: LLM saw original, but logs get redacted
            log_result = self.redaction_engine.scrub(original_prompt)
            log_prompt = log_result.redacted_text

            if log_result.has_sensitive_data:
                logger.info(
                    f"LOGS mode: Redacting sensitive data in audit logs. "
                    f"Patterns: {log_result.patterns_triggered}"
                )

            # Redact messages for logs
            if messages:
                log_messages = []
                for msg in messages:
                    redacted_msg = msg.copy()
                    if "content" in redacted_msg:
                        redacted_msg["content"] = self.redaction_engine.scrub(
                            redacted_msg["content"]
                        ).redacted_text
                    log_messages.append(redacted_msg)

            # Optionally redact response content in logs (if it echoes sensitive data)
            response_redact = self.redaction_engine.scrub(response.content)
            if response_redact.has_sensitive_data:
                log_response_content = response_redact.redacted_text

        # Log full request/response to file with tier and use_judge
        # Note: log_request_response internally calls log_routing_decision for database logging
        route_end = time.time()
        await self.audit.log_request_response(
            session_id=session_id,
            request_id=request_id,
            request={"prompt": log_prompt, "messages": log_messages},
            response={
                "content": log_response_content,
                "model": response.model,
                "usage": response.usage,
            },
            routing_decision={
                "model_used": model_used,
                "complexity_score": complexity_score,
                "impact_scope": impact_scope,
                "reasoning": reasoning,
                "decision_reason": decision_reason,
                "prompt_hash": str(prompt_hash_int),
                "reason": decision_reason,
                "model_latency_ms": latency_ms,
                "judge_latency_ms": judge_latency_ms,
                "cost_source": cost_source,
                "computed_cost": computed_cost,
            },
            cost=final_cost,
            start_time=datetime.fromtimestamp(route_start),
            end_time=datetime.fromtimestamp(route_end),
            tier=tier,
            use_judge=use_judge,
        )

        # 9. Update dynamic threshold with the decision
        self.threshold.add_decision(route_decision == "strong")
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
            hash_distance = (
                cycle_detector.recent_hashes[-1][0]
                if cycle_detector.recent_hashes
                else 0
            )
            metrics.record_cycle_detection(session_id, hash_distance)
            logger.warning(f"Cycle logged for session {session_id}")

        # 10b. Log escalation trace for strong model escalations (final route decision = "strong")
        # This captures the full decision path for debugging and analysis
        if tier == "strong":  # final_route_decision is "strong"
            # Get cycle detector state
            cycle_hash_dist = None
            cycle_rep_count = None
            if cycle_detected and cycle_detector.recent_hashes:
                cycle_hash_dist = cycle_detector.recent_hashes[-1][0]
                cycle_rep_count = len(cycle_detector.recent_hashes)

            # Create request preview (first 500 chars)
            request_preview = prompt[:500] if prompt else None

            # Log the trace
            await self.audit.log_escalation_trace(
                session_id=session_id,
                request_id=request_id,
                request_preview=request_preview,
                cycle_detected=cycle_detected,
                cycle_hash_distance=cycle_hash_dist,
                cycle_repetition_count=cycle_rep_count,
                cache_hit=cache_hit,
                cache_confidence=cache_confidence,
                cache_recommendation=cache_based_routing if cache_skip_judge else None,
                cache_weak_calls=0,  # TODO: Track this if semantic cache stores stats
                cache_strong_calls=0,  # TODO: Track this if semantic cache stores stats
                judge_invoked=(not judge_skipped),
                judge_complexity_score=complexity_score if not judge_skipped else None,
                judge_impact_scope=impact_scope if not judge_skipped else None,
                judge_reasoning=reasoning if not judge_skipped else None,
                judge_latency_ms=judge_latency_ms,
                initial_route_decision=initial_route_decision,
                final_route_decision="strong",
                escalation_reason=decision_reason,
                model_used=model_used,
            )
            logger.info(
                f"Escalation trace logged for strong model escalation (session: {session_id}, request: {request_id})"
            )

        # 11. Record semantic cache entry with full request/response metadata
        # SKIP caching if cycle detection forced the routing decision to avoid
        # building false "confident history" for cycle-detected requests
        total_latency_ms = (time.time() - route_start) * 1000
        total_tokens = (
            response.usage.get("total_tokens", 0)
            if hasattr(response, "usage") and response.usage
            else 0
        )

        # Record overall request latency for successful requests
        if response and hasattr(response, "content") and response.content:
            metrics.record_event(
                "overall_request_latency",
                {
                    "session_id": session_id,
                    "request_id": request_id,
                    "model_used": model_used,
                    "tier": tier,
                    "latency_ms": total_latency_ms,
                },
            )

        if cycle_detected:
            logger.info(
                f"Skipping semantic cache recording for cycle-detected request "
                f"(prevents false confident history)"
            )
            # Use a placeholder stats object for metrics
            stats = type(
                "obj",
                (object,),
                {
                    "semantic_hash": semantic_hash,
                },
            )
        else:
            stats = self.semantic_cache.record_interaction(
                prompt=prompt,
                context=messages,
                response_text=response.content,
                model_used=model_used,
                latency_ms=total_latency_ms,
                judge_invoked=not judge_skipped,
                judge_latency_ms=judge_latency_ms,
                complexity_score=complexity_score,
                impact_scope=impact_scope,
                cost=final_cost,
                total_tokens=total_tokens,
            )
            # Record events are writes, not cache hits
            metrics.record_semantic_cache_event(
                "record",
                stats.semantic_hash,
                False,
                self.semantic_cache.confidence_for_hash(stats.semantic_hash),
            )

        return {
            "model_used": model_used,
            "response": response,
            "complexity_score": complexity_score,
            "impact_scope": impact_scope,
            "reasoning": reasoning,
            "cost": final_cost,
            "cost_source": cost_source,
            "computed_cost": computed_cost,
            "session_cost": session_cost,
            "cycle_detected": cycle_detected,
            "decision_reason": decision_reason,
            "tier": tier,
            "use_judge": use_judge,
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
            effective_score = complexity_score - 0.15
            logger.debug(
                f"Strict mode: adjusting complexity from {complexity_score:.3f} to {effective_score:.3f}"
            )

        # Basic threshold rule with effective score
        if effective_score < threshold:
            return "weak"

        # If we are in strict mode, also require HIGH impact to escalate
        if strict_mode and impact_scope != "HIGH":
            logger.debug(
                f"Strict mode: impact_scope {impact_scope} != HIGH, downgrading to weak."
            )
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
            reason_parts.append(
                f"complexity_score {complexity_score:.3f} >= threshold {threshold:.3f}"
            )
            if strict_mode:
                if impact_scope == "HIGH":
                    reason_parts.append("strict mode but impact_scope is HIGH")
                else:
                    reason_parts.append(
                        "strict mode and impact_scope not HIGH -> downgraded"
                    )
            else:
                reason_parts.append(f"impact_scope {impact_scope}")
        else:
            reason_parts.append(
                f"complexity_score {complexity_score:.3f} < threshold {threshold:.3f}"
            )

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
        decisions = (
            self.db.query(RoutingDecision).filter_by(session_id=session_id).all()
        )
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
    tier: Optional[str] = None,
    use_judge: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    High-level function that creates a database session and routes a single request.

    Args:
        session_id: Unique session identifier
        prompt: User prompt text
        messages: List of message dictionaries
        request_id: Unique request identifier
        client_ip: Client IP address
        tier: User tier ('free', 'paid', 'premium')
        use_judge: Force judge call (true), skip judge (false), or conditional mode (None)
    """
    with get_db() as db:
        router = Router(db)
        # Ensure session exists with correct tier before routing
        if tier:
            router.budget.get_or_create_session(
                session_id, client_ip=client_ip, tier=tier
            )
        result = await router.route(
            session_id, prompt, messages, request_id, client_ip, use_judge, tier
        )
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
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    # 2. Create a router
    router = Router(db)

    # 3. Mock the judge to return a deterministic result
    router.judge.judge = AsyncMock(return_value=(0.8, "HIGH", "Demo reasoning"))

    # 4. Mock the LLM clients
    mock_response = LLMResponse(
        content="This is a mocked response from the LLM.", model="mock", cost=0.42
    )
    mock_client = AsyncMock()
    mock_client.chat_completion = AsyncMock(return_value=mock_response)

    # Patch the client getter to return our mock client
    with patch("__main__.get_client_for_key_instance", return_value=mock_client):
        # 5. Run the router with a simple prompt
        print("=== SentinelRouter Demo Flow ===")
        print("Session: demo-session-001")
        print("Prompt: 'What is the meaning of life?'")
        print()

        result = await router.route(
            session_id="demo-session-001",
            prompt="What is the meaning of life?",
            messages=[{"role": "user", "content": "What is the meaning of life?"}],
        )

        # 6. Print the result
        print("--- Routing Result ---")
        for key, value in result.items():
            if key == "response":
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
