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
from pydantic import BaseModel, Field
import uvicorn

from .database import get_db, init_db
from .router_logic import Router, route_request
from .logging_audit import setup_logging
from .config import settings
from .budget import BudgetKillSwitch
from .models import Session as SessionModel, RoutingDecision

# Setup logging
setup_logging()
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
cors_origins = settings.cors_origins.split(",") if settings.cors_origins != "*" else ["*"]
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
    model: Optional[str] = Field(None, description="Model to use (ignored, routing decides)")
    messages: List[ChatMessage]
    temperature: Optional[float] = Field(0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1)
    stream: Optional[bool] = False
    session_id: Optional[str] = Field(None, description="Custom session ID for tracking")
    tier: Optional[str] = Field("free", description="User tier: 'free', 'paid', or 'premium'")
    use_judge: Optional[bool] = Field(None, description="Force judge call (true) or skip judge (false). If None, uses conditional mode with 15s timeout.")

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
# Endpoints
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize database and other resources on startup."""
    logger.info("Starting SentinelRouter server...")
    init_db()
    logger.info("Database initialized.")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    from .clients import close_clients
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
        ]
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
        strong_count = db.query(RoutingDecision).filter(RoutingDecision.model_used == "anthropic").count()
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
        session = db.query(SessionModel).filter(SessionModel.session_id == session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        decisions = db.query(RoutingDecision).filter(RoutingDecision.session_id == session_id).all()
        strong_count = sum(1 for d in decisions if d.model_used == "anthropic")
        weak_count = len(decisions) - strong_count

        return {
            "session_id": session.session_id,
            "client_ip": session.client_ip,
            "created_at": session.created_at.isoformat() if session.created_at else None,
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
        decisions = db.query(RoutingDecision).filter(RoutingDecision.session_id == session_id).all()
        if not decisions:
            raise HTTPException(status_code=404, detail="No decisions found for this session")

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
    # Extract session ID from header or request body
    session_id = request.session_id or fastapi_request.headers.get("X-Session-ID")
    if not session_id:
        # Generate a session ID based on client IP (simple approach)
        client_ip = fastapi_request.client.host
        # Use deterministic session ID based on IP (can be overridden by X-Session-ID header)
        import hashlib
        ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()[:8]
        session_id = f"ip_{client_ip}_{ip_hash}"
        logger.info(f"No session ID provided, generated deterministic ID: {session_id}")

    # Convert messages to list of dicts for router
    messages = [msg.dict() for msg in request.messages]

    # Extract prompt from messages (simple concatenation for judge)
    user_messages = [msg for msg in messages if msg["role"] == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found in request.")
    prompt = user_messages[-1]["content"]

    try:
        # Route the request
        result = await route_request(
            session_id=session_id,
            prompt=prompt,
            messages=messages,
            request_id=str(uuid.uuid4()),
            client_ip=fastapi_request.client.host,
            tier=request.tier,
            use_judge=request.use_judge,
        )
    except ValueError as e:
        # Budget exceeded or other business logic error
        raise HTTPException(status_code=429, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error during routing")
        raise HTTPException(status_code=500, detail="Internal server error")

    # Prepare OpenAI‑style response
    llm_response = result["response"]
    response_id = f"chatcmpl-{uuid.uuid4()}"
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
    return JSONResponse(content=response_obj.dict(), headers=headers)

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
        daemon=True
    )
    dashboard_thread.start()
    logger.info("Dashboard server started on http://localhost:8001")
    
    # Start main API server
    uvicorn.run(
        "sentinelrouter.server:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=False,
    )