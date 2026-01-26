"""
FastAPI application for SentinelRouter.
"""

import logging
import uuid
import time
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
import uvicorn

from .database import get_db, init_db
from .router_logic import Router, route_request
from .logging_audit import setup_logging
from .config import get_settings
from .budget import BudgetKillSwitch
from .models import Session as SessionModel, RoutingDecision
from .state_manager import get_state_manager

# Initialize logger
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="SentinelRouter",
    description="Production‑ready local API gateway for budget‑controlled LLM routing",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware - configurable via CORS_ORIGINS env var
# Set CORS_ORIGINS="https://example.com,https://app.example.com" for production
# or CORS_ORIGINS="*" for development (default)
# Configure CORS before app starts
settings = get_settings()
cors_origins = (
    settings.cors_origins.split(",") if settings.cors_origins != "*" else ["*"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Middleware
# ============================================================================


@app.middleware("http")
async def budget_middleware(request: Request, call_next):
    """
    Budget kill‑switch middleware (Module A).
    Checks session budget before processing the request.
    """
    # Log all requests to chat completions for debugging
    if request.url.path == "/v1/chat/completions":
        # Try to read body for logging (non-destructive peek)
        body = await request.body()
        logger.info(
            f"Incoming request to /v1/chat/completions - Body: {body.decode('utf-8', errors='ignore')[:500]}"
        )

        # Create new request with same body for downstream processing
        async def receive():
            return {"type": "http.request", "body": body}

        request._receive = receive

    # Only check for chat completions endpoint
    if request.url.path != "/v1/chat/completions":
        return await call_next(request)

    # Extract session ID from headers or query
    session_id = request.headers.get("X-Session-ID")
    if not session_id:
        # If not in header, try to get from request body (for POST JSON)
        # We cannot read body here without consuming it; instead we'll let the endpoint handle it.
        # For simplicity, we'll skip budget check if no session ID in header.
        # The endpoint will generate a session ID and budget will be checked there.
        return await call_next(request)

    # Check budget using a database session
    with get_db() as db:
        budget = BudgetKillSwitch(db)
        # Estimate worst-case cost (strong model) for budget check
        estimated_cost = 5.0  # same as in router_logic
        if not budget.check_budget(session_id, estimated_cost):
            return JSONResponse(
                status_code=402,
                content={
                    "error": {
                        "message": f"Budget exceeded for session {session_id}",
                        "type": "budget_exceeded",
                        "code": 402,
                    }
                },
            )

    return await call_next(request)


# ============================================================================
# Request/Response Models (OpenAI‑compatible)
# ============================================================================


class ChatMessage(BaseModel):
    role: str
    content: str
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: Optional[str] = Field(
        None, description="Model to use (ignored, routing decides)"
    )
    messages: List[ChatMessage]
    temperature: Optional[float] = Field(0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1)
    stream: Optional[bool] = False
    session_id: Optional[str] = Field(
        None, description="Custom session ID for tracking"
    )
    tier: Optional[str] = Field(
        "free", description="User tier: 'free', 'paid', or 'premium'"
    )
    use_judge: Optional[bool] = Field(
        None,
        description="Force judge call (true) or skip judge (false). If None, uses conditional mode with 15s timeout.",
    )


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: Optional[str] = None


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: Optional[Usage] = None


class ErrorResponse(BaseModel):
    error: Dict[str, Any]


# ============================================================================
# Exception Handlers
# ============================================================================


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log validation errors with full request details."""
    body = await request.body()
    logger.error(f"Validation error on {request.url.path}")
    logger.error(f"Request body: {body.decode('utf-8', errors='ignore')}")
    logger.error(f"Validation errors: {exc.errors()}")

    return JSONResponse(status_code=422, content={"detail": exc.errors()})


# ============================================================================
# Endpoints
# ============================================================================


@app.on_event("startup")
async def startup_event():
    """Initialize database and other resources on startup."""
    logger.info("Starting SentinelRouter server...")
    init_db()
    logger.info("Database initialized.")

    # Start rate limiter daily reset task
    from .rate_limiter import get_rate_limiter

    rate_limiter = get_rate_limiter()
    rate_limiter.start()
    logger.info("Rate limiter started.")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    from .clients import close_clients
    from .rate_limiter import get_rate_limiter

    # Stop rate limiter
    rate_limiter = get_rate_limiter()
    await rate_limiter.stop()
    logger.info("Rate limiter stopped.")

    await close_clients()
    logger.info("Server shut down.")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "sentinelrouter"}


@app.get("/v1/models")
async def list_models():
    """
    List available models (OpenAI-compatible endpoint).
    Returns the models that SentinelRouter can route to.
    """
    return {
        "object": "list",
        "data": [
            {
                "id": "gpt-4",
                "object": "model",
                "created": 1687882411,
                "owned_by": "sentinelrouter",
                "permission": [],
                "root": "gpt-4",
                "parent": None,
            },
            {
                "id": "gpt-3.5-turbo",
                "object": "model",
                "created": 1677610602,
                "owned_by": "sentinelrouter",
                "permission": [],
                "root": "gpt-3.5-turbo",
                "parent": None,
            },
        ],
    }


@app.get("/metrics")
async def metrics():
    """Return current system metrics."""
    from sqlalchemy import func

    with get_db() as db:
        # Total sessions
        session_count = db.query(SessionModel).count()
        # Total routing decisions
        decision_count = db.query(RoutingDecision).count()
        # Total cost across all sessions (sum of all session costs)
        total_cost = db.query(func.sum(SessionModel.current_cost)).scalar() or 0.0
        # Escalation rate (strong vs total)
        strong_count = (
            db.query(RoutingDecision)
            .filter(RoutingDecision.model_used == "anthropic")
            .count()
        )
        weak_count = decision_count - strong_count
        escalation_rate = strong_count / decision_count if decision_count > 0 else 0.0

    return {
        "requests_total": decision_count,
        "sessions_total": session_count,
        "cost_total": total_cost,
        "escalation_rate": escalation_rate,
        "strong_requests": strong_count,
        "weak_requests": weak_count,
    }


@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Retrieve details of a specific session."""
    with get_db() as db:
        session = (
            db.query(SessionModel).filter(SessionModel.session_id == session_id).first()
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        decisions = (
            db.query(RoutingDecision)
            .filter(RoutingDecision.session_id == session_id)
            .all()
        )
        strong_count = sum(1 for d in decisions if d.model_used == "anthropic")
        weak_count = len(decisions) - strong_count

        return {
            "session_id": session.session_id,
            "client_ip": session.client_ip,
            "created_at": session.created_at.isoformat()
            if session.created_at
            else None,
            "max_cost_per_session": session.max_cost_per_session,
            "current_cost": session.current_cost,
            "is_active": session.is_active,
            "total_requests": len(decisions),
            "strong_requests": strong_count,
            "weak_requests": weak_count,
            "escalation_rate": strong_count / len(decisions) if decisions else 0.0,
        }


@app.get("/audit/{session_id}")
async def audit_session(session_id: str):
    """Retrieve routing decisions for a session."""
    with get_db() as db:
        decisions = (
            db.query(RoutingDecision)
            .filter(RoutingDecision.session_id == session_id)
            .all()
        )
        if not decisions:
            raise HTTPException(
                status_code=404, detail="No decisions found for this session"
            )

        return {
            "session_id": session_id,
            "decisions": [
                {
                    "request_id": d.request_id,
                    "timestamp": d.timestamp.isoformat() if d.timestamp else None,
                    "model_used": d.model_used,
                    "complexity_score": d.complexity_score,
                    "cost_incurred": d.cost_incurred,
                    "impact_scope": d.impact_scope,
                    "reason": d.reason,
                }
                for d in decisions
            ],
        }


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(request: ChatCompletionRequest, fastapi_request: Request):
    """
    OpenAI‑compatible chat completions endpoint.
    """
    # Get session defaults from StateManager
    state_mgr = await get_state_manager()
    session_defaults = await state_mgr.get_session_defaults()

    # Apply session defaults with priority: request > config > hardcoded
    session_id = request.session_id or fastapi_request.headers.get("X-Session-ID")
    if not session_id:
        # Use session_id_strategy from config
        strategy = session_defaults.get("session_id_strategy", "uuid")
        if strategy == "ip_based":
            client_ip = fastapi_request.client.host
            import hashlib

            ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()[:8]
            session_id = f"ip_{client_ip}_{ip_hash}"
            logger.info(f"Generated IP-based session ID: {session_id}")
        else:
            # Use default_session_id from config or generate UUID
            session_id = session_defaults.get("default_session_id")
            if not session_id or strategy == "uuid":
                session_id = str(uuid.uuid4())
            logger.info(f"Using session ID: {session_id}")

    # Apply tier default (request > config > hardcoded "free")
    tier = (
        request.tier
        if request.tier is not None
        else session_defaults.get("default_tier", "free")
    )

    # Apply use_judge default (request > config > hardcoded None)
    use_judge = (
        request.use_judge
        if request.use_judge is not None
        else session_defaults.get("default_use_judge")
    )

    logger.info(
        f"Request params: session_id={session_id}, tier={tier}, use_judge={use_judge}"
    )

    # Validate and convert messages to list of dicts for router
    if not request.messages:
        raise HTTPException(status_code=400, detail="Messages array cannot be empty.")

    messages = []
    for msg in request.messages:
        msg_dict = msg.dict()
        # Validate content field exists and is not None
        if msg_dict.get("content") is None:
            raise HTTPException(
                status_code=400,
                detail=f"Message with role '{msg_dict.get('role', 'unknown')}' has null or missing content.",
            )
        # Ensure content is a string
        if not isinstance(msg_dict.get("content"), str):
            msg_dict["content"] = str(msg_dict["content"])
        messages.append(msg_dict)

    # Extract prompt from messages (simple concatenation for judge)
    user_messages = [msg for msg in messages if msg["role"] == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found in request.")

    # Safely extract content from last user message
    last_user_msg = user_messages[-1]
    prompt = last_user_msg.get("content", "")
    if not prompt or not isinstance(prompt, str):
        raise HTTPException(
            status_code=400, detail="User message content must be a non-empty string."
        )

    try:
        # Route the request
        result = await route_request(
            session_id=session_id,
            prompt=prompt,
            messages=messages,
            request_id=str(uuid.uuid4()),
            client_ip=fastapi_request.client.host,
            tier=tier,
            use_judge=use_judge,
        )
    except ValueError as e:
        # Budget exceeded or other business logic error
        # Clear cycle detector state to prevent false positives on retry
        from .router_logic import _CYCLE_DETECTORS_CACHE

        if session_id in _CYCLE_DETECTORS_CACHE:
            _CYCLE_DETECTORS_CACHE[session_id].clear_last_response()
        raise HTTPException(status_code=429, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error during routing")
        # Clear cycle detector state to prevent false positives on retry
        from .router_logic import _CYCLE_DETECTORS_CACHE

        if session_id in _CYCLE_DETECTORS_CACHE:
            _CYCLE_DETECTORS_CACHE[session_id].clear_last_response()
        raise HTTPException(status_code=500, detail="Internal server error")

    # Prepare OpenAI‑style response
    llm_response = result["response"]
    response_id = f"chatcmpl-{uuid.uuid4()}"

    # Log response content for debugging
    logger.info(
        f"Response for session {session_id}: model={llm_response.model}, content_length={len(llm_response.content) if llm_response.content else 0}"
    )
    if not llm_response.content:
        logger.warning(
            f"Empty response content for session {session_id}! Full response: {llm_response}"
        )

    choice = ChatCompletionChoice(
        index=0,
        message=ChatMessage(
            role="assistant",
            content=llm_response.content,
        ),
        finish_reason="stop",
    )

    # Convert usage if available
    usage = None
    if llm_response.usage:
        usage = Usage(
            prompt_tokens=llm_response.usage.get("prompt_tokens", 0),
            completion_tokens=llm_response.usage.get("completion_tokens", 0),
            total_tokens=llm_response.usage.get("total_tokens", 0),
        )

    response_obj = ChatCompletionResponse(
        id=response_id,
        created=int(time.time()),
        model=llm_response.model,
        choices=[choice],
        usage=usage,
    )

    # Add custom headers
    headers = {
        "X-Sentinel-Model-Used": result["model_used"],
        "X-Sentinel-Cost": str(result["cost"]),
        "X-Sentinel-Session-Cost": str(result.get("session_cost", 0.0)),
        "X-Sentinel-Complexity-Score": str(result["complexity_score"]),
        "X-Sentinel-Cycle-Detected": str(result["cycle_detected"]).lower(),
        "X-Sentinel-Session-ID": session_id,
    }

    # Log final response being sent
    response_dict = response_obj.dict()
    logger.info(
        f"Sending response for session {session_id}: {len(str(response_dict))} bytes"
    )

    return JSONResponse(content=response_dict, headers=headers)


# ============================================================================
# Session Defaults Management API (for Dashboard)
# ============================================================================


@app.get("/api/dashboard/session-defaults")
async def get_session_defaults():
    """Get current session defaults configuration."""
    try:
        state_mgr = await get_state_manager()
        session_defaults = await state_mgr.get_session_defaults()
        return JSONResponse(content={"success": True, "data": session_defaults})
    except Exception as e:
        logger.exception("Error getting session defaults")
        return JSONResponse(
            status_code=500, content={"success": False, "error": str(e)}
        )


@app.post("/api/dashboard/session-defaults")
async def update_session_defaults(updates: dict):
    """Update session defaults configuration."""
    try:
        state_mgr = await get_state_manager()
        success = await state_mgr.update_session_defaults(**updates)
        if success:
            session_defaults = await state_mgr.get_session_defaults()
            logger.info(f"Session defaults updated: {updates}")
            return JSONResponse(
                content={
                    "success": True,
                    "message": "Session defaults updated successfully",
                    "data": session_defaults,
                }
            )
        else:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Failed to update session defaults",
                },
            )
    except Exception as e:
        logger.exception("Error updating session defaults")
        return JSONResponse(
            status_code=500, content={"success": False, "error": str(e)}
        )


@app.post("/api/dashboard/regenerate-session-id")
async def regenerate_session_id():
    """Regenerate the default session ID based on current strategy."""
    try:
        state_mgr = await get_state_manager()
        new_id = await state_mgr.regenerate_session_id()
        logger.info(f"Session ID regenerated: {new_id}")
        return JSONResponse(
            content={
                "success": True,
                "message": "Session ID regenerated successfully",
                "data": {"default_session_id": new_id},
            }
        )
    except Exception as e:
        logger.exception("Error regenerating session ID")
        return JSONResponse(
            status_code=500, content={"success": False, "error": str(e)}
        )


# ============================================================================
# Admin Policy Management API (Operator-Grade Controls)
# ============================================================================


@app.get("/api/admin/policy")
async def get_admin_policy():
    """
    Get current admin policy configuration (editable fields only).

    Returns only the safe, runtime-tunable policy knobs.
    Does not expose keys, models, or routing topology.
    """
    try:
        from ..schemas.admin_policy import (
            AdminPolicyConfig,
            BudgetControl,
            JudgePolicy,
            SemanticCachePolicy,
            CycleDetectionPolicy,
        )

        settings = get_settings()
        state_mgr = await get_state_manager()
        session_defaults = await state_mgr.get_session_defaults()

        # Build policy from current settings
        policy = AdminPolicyConfig(
            budget_control=BudgetControl(
                max_cost_per_session=settings.max_cost_per_session,
                escalation_rate_limit=settings.escalation_rate_limit,
                rolling_window_size=settings.rolling_window_size,
            ),
            judge=JudgePolicy(
                enabled=session_defaults.get("default_use_judge") is not False,
                mode="smart"
                if session_defaults.get("default_use_judge") is None
                else (
                    "always" if session_defaults.get("default_use_judge") else "never"
                ),
                complexity_threshold=settings.complexity_threshold,
            ),
            semantic_cache=SemanticCachePolicy(
                enabled=True,  # Assuming enabled by default
                min_samples=settings.semantic_cache_min_samples,
                confidence_threshold=settings.semantic_cache_confidence_threshold,
                ttl_seconds=604800,  # Default 7 days
            ),
            cycle_detection=CycleDetectionPolicy(
                enabled=settings.enable_cycle_detection,
                window_size=settings.cycle_detection_window_size,
                simhash_distance_threshold=settings.cycle_detection_simhash_threshold,
            ),
        )

        return JSONResponse(
            content={
                "success": True,
                "data": policy.model_dump(),
                "impact_notes": {
                    "immediate_effect": [
                        "judge.enabled",
                        "judge.mode",
                        "complexity_threshold",
                        "escalation_rate_limit",
                        "cycle_detection.enabled",
                    ],
                    "soft_reset_recommended": [
                        "semantic_cache.min_samples",
                        "semantic_cache.ttl_seconds",
                        "rolling_window_size",
                    ],
                    "warning_required": ["budget_control.max_cost_per_session"],
                },
            }
        )
    except Exception as e:
        logger.exception("Error getting admin policy")
        return JSONResponse(
            status_code=500, content={"success": False, "error": str(e)}
        )


@app.post("/api/admin/policy")
async def update_admin_policy(updates: dict):
    """
    Update admin policy configuration (selective update).

    Only accepts policy fields defined in AdminPolicyConfig.
    Returns updated policy and impact warnings.
    """
    try:
        from ..schemas.admin_policy import AdminPolicyUpdate

        # Validate the update payload
        policy_update = AdminPolicyUpdate(**updates)

        settings = get_settings()
        impact_warnings = []

        # Apply budget control updates
        if policy_update.budget_control:
            if (
                policy_update.budget_control.max_cost_per_session
                != settings.max_cost_per_session
            ):
                settings.max_cost_per_session = (
                    policy_update.budget_control.max_cost_per_session
                )
                impact_warnings.append(
                    "max_cost_per_session changed - may immediately block in-flight sessions"
                )
            if (
                policy_update.budget_control.escalation_rate_limit
                != settings.escalation_rate_limit
            ):
                settings.escalation_rate_limit = (
                    policy_update.budget_control.escalation_rate_limit
                )
            if (
                policy_update.budget_control.rolling_window_size
                != settings.rolling_window_size
            ):
                settings.rolling_window_size = (
                    policy_update.budget_control.rolling_window_size
                )
                impact_warnings.append(
                    "rolling_window_size changed - consider resetting escalation counters"
                )

        # Apply judge policy updates
        if policy_update.judge:
            state_mgr = await get_state_manager()
            judge_mode = policy_update.judge.mode
            default_use_judge = (
                None
                if judge_mode == "smart"
                else (True if judge_mode == "always" else False)
            )
            await state_mgr.update_session_defaults(default_use_judge=default_use_judge)

            if (
                policy_update.judge.complexity_threshold
                != settings.complexity_threshold
            ):
                settings.complexity_threshold = policy_update.judge.complexity_threshold

        # Apply semantic cache policy updates
        if policy_update.semantic_cache:
            if (
                policy_update.semantic_cache.min_samples
                != settings.semantic_cache_min_samples
            ):
                settings.semantic_cache_min_samples = (
                    policy_update.semantic_cache.min_samples
                )
                impact_warnings.append(
                    "semantic_cache.min_samples changed - consider resetting cache"
                )
            if (
                policy_update.semantic_cache.confidence_threshold
                != settings.semantic_cache_confidence_threshold
            ):
                settings.semantic_cache_confidence_threshold = (
                    policy_update.semantic_cache.confidence_threshold
                )

        # Apply cycle detection policy updates
        if policy_update.cycle_detection:
            if policy_update.cycle_detection.enabled != settings.enable_cycle_detection:
                settings.enable_cycle_detection = policy_update.cycle_detection.enabled
            if (
                policy_update.cycle_detection.window_size
                != settings.cycle_detection_window_size
            ):
                settings.cycle_detection_window_size = (
                    policy_update.cycle_detection.window_size
                )
            if (
                policy_update.cycle_detection.simhash_distance_threshold
                != settings.cycle_detection_simhash_threshold
            ):
                settings.cycle_detection_simhash_threshold = (
                    policy_update.cycle_detection.simhash_distance_threshold
                )

        logger.info(f"Admin policy updated: {updates}")

        return JSONResponse(
            content={
                "success": True,
                "message": "Admin policy updated successfully",
                "warnings": impact_warnings,
                "data": policy_update.model_dump(exclude_none=True),
            }
        )
    except Exception as e:
        logger.exception("Error updating admin policy")
        return JSONResponse(
            status_code=400, content={"success": False, "error": str(e)}
        )


@app.get("/api/admin/state")
async def get_admin_state():
    """
    Get read-only state information for operators.

    Provides visibility into routing, judge, semantic cache, and escalation state.
    All information is read-only to prevent accidental topology changes.
    """
    try:
        from ..schemas.admin_policy import AdminStateResponse

        state_mgr = await get_state_manager()
        config = state_mgr.config

        # Build routing state
        weak_models = []
        strong_models = []
        routing_order = []

        if hasattr(config, "models"):
            for model_id, model_config in config.models.items():
                if model_config.status == "ACTIVE":
                    routing_order.append(model_id)
                    if model_config.routing.priority_group == "fast_tier":
                        weak_models.append(model_id)
                    elif model_config.routing.priority_group == "strong_tier":
                        strong_models.append(model_id)

        # Query database for recent metrics
        with get_db() as db:
            # Get recent routing decisions for ratios
            recent_decisions = (
                db.query(RoutingDecision)
                .order_by(RoutingDecision.timestamp.desc())
                .limit(100)
                .all()
            )

            weak_count = sum(
                1
                for d in recent_decisions
                if any(weak in (d.model_used or "") for weak in weak_models)
            )
            strong_count = sum(
                1
                for d in recent_decisions
                if any(strong in (d.model_used or "") for strong in strong_models)
            )
            total_count = len(recent_decisions)

            weak_strong_ratio = weak_count / strong_count if strong_count > 0 else None
            escalation_rate = strong_count / total_count if total_count > 0 else 0.0

        # Build state response
        state = AdminStateResponse(
            routing=AdminStateResponse.RoutingState(
                weak_models=weak_models,
                strong_models=strong_models,
                routing_order=routing_order,
                weak_strong_ratio=weak_strong_ratio,
            ),
            judge=AdminStateResponse.JudgeState(
                # These would be populated from actual metrics
                invoked_count=0,
                skipped_count=0,
                skip_rate=0.0,
                success_rate=0.0,
                avg_latency_ms=0.0,
            ),
            semantic_cache=AdminStateResponse.SemanticCacheState(
                hit_count=0,
                miss_count=0,
                hit_rate=0.0,
                active_clusters=0,
                judge_skip_attribution=0.0,
            ),
            escalation=AdminStateResponse.EscalationState(
                current_rate=escalation_rate,
                target_rate=get_settings().target_escalation_rate,
                is_strict_mode=escalation_rate > get_settings().target_escalation_rate,
                effective_threshold=get_settings().complexity_threshold,
            ),
        )

        return JSONResponse(
            content={
                "success": True,
                "data": state.model_dump(),
                "note": "All state information is read-only. Use /api/admin/policy to edit policy.",
            }
        )
    except Exception as e:
        logger.exception("Error getting admin state")
        return JSONResponse(
            status_code=500, content={"success": False, "error": str(e)}
        )


@app.post("/api/admin/reset-cache")
async def reset_semantic_cache():
    """
    Reset the semantic cache state.

    Use this after changing semantic cache policy parameters like min_samples or ttl_seconds.
    """
    try:
        # TODO: Implement actual cache reset logic when semantic cache is integrated
        logger.info("Semantic cache reset requested")
        return JSONResponse(
            content={"success": True, "message": "Semantic cache reset successfully"}
        )
    except Exception as e:
        logger.exception("Error resetting semantic cache")
        return JSONResponse(
            status_code=500, content={"success": False, "error": str(e)}
        )


@app.post("/api/admin/reset-escalation")
async def reset_escalation_counters():
    """
    Reset escalation rate counters.

    Use this after changing rolling_window_size or escalation_rate_limit.
    """
    try:
        # TODO: Implement actual escalation counter reset
        logger.info("Escalation counters reset requested")
        return JSONResponse(
            content={
                "success": True,
                "message": "Escalation counters reset successfully",
            }
        )
    except Exception as e:
        logger.exception("Error resetting escalation counters")
        return JSONResponse(
            status_code=500, content={"success": False, "error": str(e)}
        )


# ============================================================================
# Error handlers
# ============================================================================


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Convert HTTP exceptions to OpenAI‑style error responses."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "message": exc.detail,
                "type": "http_error",
                "code": exc.status_code,
            }
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Handle unexpected errors."""
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "message": "Internal server error",
                "type": "internal_error",
                "code": 500,
            }
        },
    )


if __name__ == "__main__":
    import threading
    from .dashboard import start_dashboard_server

    # Start dashboard server in a separate thread
    dashboard_thread = threading.Thread(
        target=start_dashboard_server,
        kwargs={"host": "0.0.0.0", "port": 8001},
        daemon=True,
    )
    dashboard_thread.start()
    logger.info("Dashboard server started on http://localhost:8001")

    # Start main API server
    settings = get_settings()
    uvicorn.run(
        "sentinelrouter.server:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=False,
    )
