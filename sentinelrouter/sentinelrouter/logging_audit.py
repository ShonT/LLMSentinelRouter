"""
Logging and audit system for SentinelRouter.

Structured JSON logging to files and database audit trail.
"""

import asyncio
import json
import logging
import logging.handlers
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session as DBSession

from .models import RoutingDecision, EscalationLog, EscalationTrace
from .config import get_settings


# Lazy initialization of logs_dir to avoid validation errors during imports
def get_logs_dir():
    """Return the logs directory, initializing if necessary."""
    return Path(get_settings().log_dir)


# Thread pool for asynchronous file I/O
_executor = ThreadPoolExecutor(max_workers=2)


class JSONFormatter(logging.Formatter):
    """
    Formatter that outputs JSON strings.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_object = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if hasattr(record, "extra"):
            log_object.update(record.extra)
        if record.exc_info:
            log_object["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_object, ensure_ascii=False)


def setup_logging() -> None:
    """
    Configure the root logger with a rotating file handler (JSON) and console handler.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, get_settings().log_level.upper()))

    # Remove any existing handlers
    root_logger.handlers.clear()

    # File handler (JSON) - only if enabled
    if get_settings().enable_file_logging:
        logs_dir = get_logs_dir()  # Access logs_dir at runtime
        log_file = logs_dir / "sentinelrouter.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=get_settings().log_rotation_max_bytes,
            backupCount=get_settings().log_rotation_backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(file_handler)

    # Console handler (human‑readable)
    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    logging.info("Logging configured (level=%s)", get_settings().log_level)


class AuditLogger:
    """
    Records routing decisions and threshold adjustments to the database.
    """

    def __init__(self, db_session: DBSession):
        self.db = db_session

    def log_routing_decision(
        self,
        session_id: str,
        request_id: str,
        model_used: str,
        complexity_score: float,
        cost_incurred: float,
        prompt_hash: str,
        impact_scope: Optional[str] = None,
        reason: Optional[str] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        request_latency_ms: float = 0.0,
        model_latency_ms: float = 0.0,
        judge_latency_ms: Optional[float] = None,
    ) -> None:
        """
        Write a routing decision to the database with token and latency tracking.
        """
        decision = RoutingDecision(
            session_id=session_id,
            request_id=request_id,
            model_used=model_used,
            complexity_score=complexity_score,
            cost_incurred=cost_incurred,
            prompt_hash=prompt_hash,
            impact_scope=impact_scope,
            reason=reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            request_latency_ms=request_latency_ms,
            model_latency_ms=model_latency_ms,
            judge_latency_ms=judge_latency_ms,
        )
        self.db.add(decision)
        self.db.commit()
        logging.debug(
            f"Logged routing decision for session {session_id}, model {model_used}, "
            f"tokens: {total_tokens}, latency: {request_latency_ms:.2f}ms"
        )

    def log_escalation(
        self,
        session_id: str,
        escalation_rate: float,
        threshold_before: float,
        threshold_after: float,
        reason: Optional[str] = None,
    ) -> None:
        """
        Log a threshold adjustment to the escalation_log table.
        """
        log_entry = EscalationLog(
            session_id=session_id,
            escalation_rate=escalation_rate,
            threshold_before=threshold_before,
            threshold_after=threshold_after,
            reason=reason,
        )
        self.db.add(log_entry)
        self.db.commit()
        logging.info(
            f"Logged escalation adjustment for session {session_id}: "
            f"rate {escalation_rate:.2%}, threshold {threshold_before:.3f} -> {threshold_after:.3f}"
        )

    def log_cycle_detection(
        self,
        session_id: str,
        prompt_hash: str,
        response_hash: str,
    ) -> None:
        """
        Log a cycle detection event (optional).
        This could be stored in a separate table, but for simplicity we just log.
        """
        logging.warning(
            f"Cycle detected in session {session_id}: "
            f"prompt_hash={prompt_hash}, response_hash={response_hash}"
        )
    
    def log_escalation_trace(
        self,
        session_id: str,
        request_id: str,
        request_preview: Optional[str] = None,
        cycle_detected: bool = False,
        cycle_hash_distance: Optional[float] = None,
        cycle_repetition_count: Optional[int] = None,
        cache_hit: bool = False,
        cache_confidence: Optional[float] = None,
        cache_recommendation: Optional[str] = None,
        cache_weak_calls: int = 0,
        cache_strong_calls: int = 0,
        judge_invoked: bool = False,
        judge_complexity_score: Optional[float] = None,
        judge_impact_scope: Optional[str] = None,
        judge_reasoning: Optional[str] = None,
        judge_latency_ms: Optional[float] = None,
        initial_route_decision: str = "weak",
        final_route_decision: str = "strong",
        escalation_reason: Optional[str] = None,
        model_used: Optional[str] = None,
    ) -> None:
        """
        Log a detailed escalation trace for strong model escalations.
        Records the full decision path including cycle detection, cache, and judge results.
        """
        trace = EscalationTrace(
            session_id=session_id,
            request_id=request_id,
            request_preview=request_preview,
            cycle_detected=cycle_detected,
            cycle_hash_distance=cycle_hash_distance,
            cycle_repetition_count=cycle_repetition_count,
            cache_hit=cache_hit,
            cache_confidence=cache_confidence,
            cache_recommendation=cache_recommendation,
            cache_weak_calls=cache_weak_calls,
            cache_strong_calls=cache_strong_calls,
            judge_invoked=judge_invoked,
            judge_complexity_score=judge_complexity_score,
            judge_impact_scope=judge_impact_scope,
            judge_reasoning=judge_reasoning,
            judge_latency_ms=judge_latency_ms,
            initial_route_decision=initial_route_decision,
            final_route_decision=final_route_decision,
            escalation_reason=escalation_reason,
            model_used=model_used,
        )
        self.db.add(trace)
        self.db.commit()
        logging.info(
            f"Logged escalation trace for session {session_id}, request {request_id}: "
            f"{initial_route_decision} -> {final_route_decision} (reason: {escalation_reason})"
        )


class RequestResponseLogger:
    """
    Asynchronous file‑based JSON logging for each request/response.
    """

    def __init__(self, log_dir: Path):
        self.log_dir = log_dir
        self.log_dir.mkdir(exist_ok=True)

    def _generate_filename(self, timestamp: datetime, model_used: str, cost: float) -> str:
        """
        Generate filename pattern: {timestamp}_{model_used}_{cost}.json
        Timestamp format: YYYYMMDD_HHMMSS_fff
        """
        ts_str = timestamp.strftime("%Y%m%d_%H%M%S_%f")[:-3]  # keep milliseconds (3 digits)
        cost_str = f"{cost:.2f}"
        # Replace dots with underscores for safety? Keep dot for decimal.
        # Remove any characters that are not safe for filenames.
        safe_model = model_used.replace("/", "_").replace("\\", "_")
        return f"{ts_str}_{safe_model}_{cost_str}.json"

    async def log_request_response(
        self,
        session_id: str,
        request_id: str,
        request: Dict[str, Any],
        response: Dict[str, Any],
        routing_decision: Dict[str, Any],
        cost: float,
        start_time: datetime,
        end_time: datetime,
        tier: Optional[str] = None,
        use_judge: Optional[bool] = None,
    ) -> None:
        """
        Log a request/response pair to a JSON file.
        This runs in a background thread to avoid blocking.
        """
        model_used = routing_decision.get("model_used", "unknown")
        filename = self._generate_filename(start_time, model_used, cost)
        filepath = self.log_dir / filename

        log_entry = {
            "session_id": session_id,
            "request_id": request_id,
            "timestamp_start": start_time.isoformat(),
            "timestamp_end": end_time.isoformat(),
            "tier": tier,
            "use_judge": use_judge,
            "request": request,
            "response": response,
            "routing_decision": routing_decision,
            "cost": cost,
        }

        # Write asynchronously using thread pool
        def write_file():
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(log_entry, f, ensure_ascii=False, indent=2)

        await asyncio.get_event_loop().run_in_executor(_executor, write_file)
        logging.debug(f"Request/response logged to {filepath}")


class LoggingAudit:
    """
    Unified logging and audit facade that combines database audit and file logging.
    """

    def __init__(self, db_session: DBSession):
        self.db = db_session
        self.audit_logger = AuditLogger(db_session)
        logs_dir = get_logs_dir()
        requests_logs_dir = logs_dir / "requests"
        requests_logs_dir.mkdir(parents=True, exist_ok=True)
        self.file_logger = RequestResponseLogger(requests_logs_dir)
        self.enable_file_logging = get_settings().enable_file_logging

    async def log_request_response(
        self,
        session_id: str,
        request_id: str,
        request: Dict[str, Any],
        response: Dict[str, Any],
        routing_decision: Dict[str, Any],
        cost: float,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        tier: Optional[str] = None,
        use_judge: Optional[bool] = None,
    ) -> None:
        """
        Log a request/response to both database and file.
        """
        start_time = start_time or datetime.utcnow()
        end_time = end_time or datetime.utcnow()
        
        # Calculate request latency from start/end times
        request_latency_ms = (end_time - start_time).total_seconds() * 1000

        # Extract token and latency data from response usage
        usage = response.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", input_tokens + output_tokens)
        
        # Get latencies from routing_decision
        model_latency_ms = routing_decision.get("model_latency_ms", 0.0)
        judge_latency_ms = routing_decision.get("judge_latency_ms")

        # Database logging (synchronous but run in thread to avoid blocking)
        await asyncio.to_thread(
            self.audit_logger.log_routing_decision,
            session_id=session_id,
            request_id=request_id,
            model_used=routing_decision.get("model_used"),
            complexity_score=routing_decision.get("complexity_score", 0.0),
            cost_incurred=cost,
            prompt_hash=routing_decision.get("prompt_hash", ""),
            impact_scope=routing_decision.get("impact_scope"),
            reason=routing_decision.get("reason"),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            request_latency_ms=request_latency_ms,
            model_latency_ms=model_latency_ms,
            judge_latency_ms=judge_latency_ms,
        )

        # File logging (asynchronous)
        if self.enable_file_logging:
            await self.file_logger.log_request_response(
                session_id=session_id,
                request_id=request_id,
                request=request,
                response=response,
                routing_decision=routing_decision,
                cost=cost,
                start_time=start_time,
                end_time=end_time,
                tier=tier,
                use_judge=use_judge,
            )

    def log_routing_decision(
        self,
        session_id: str,
        request_id: str,
        model_used: str,
        complexity_score: float,
        cost_incurred: float,
        prompt_hash: str = "",
        impact_scope: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> None:
        """
        Delegate to AuditLogger.log_routing_decision (synchronous).
        """
        self.audit_logger.log_routing_decision(
            session_id=session_id,
            request_id=request_id,
            model_used=model_used,
            complexity_score=complexity_score,
            cost_incurred=cost_incurred,
            prompt_hash=prompt_hash,
            impact_scope=impact_scope,
            reason=reason,
        )

    async def log_escalation(
        self,
        session_id: str,
        escalation_rate: float,
        threshold_before: float,
        threshold_after: float,
        reason: Optional[str] = None,
    ) -> None:
        """
        Log a threshold adjustment to the database and log a message.
        """
        # Database logging (synchronous, run in thread)
        await asyncio.to_thread(
            self.audit_logger.log_escalation,
            session_id=session_id,
            escalation_rate=escalation_rate,
            threshold_before=threshold_before,
            threshold_after=threshold_after,
            reason=reason,
        )
        # Also log to console (via logging.info)
        logging.info(
            f"Escalation adjustment for session {session_id}: "
            f"rate {escalation_rate:.2%}, threshold {threshold_before:.3f} -> {threshold_after:.3f}"
        )

    async def log_budget_warning(self, session_id: str, current_cost: float, max_cost: float) -> None:
        """
        Log a budget warning.
        """
        logging.warning(
            f"Budget warning for session {session_id}: "
            f"current cost {current_cost:.2f}, max {max_cost:.2f}"
        )

    async def log_cycle_detection(self, session_id: str, prompt_hash: str, response_hash: str) -> None:
        """
        Log a cycle detection event.
        """
        # Delegate to underlying audit logger
        await asyncio.to_thread(
            self.audit_logger.log_cycle_detection,
            session_id=session_id,
            prompt_hash=prompt_hash,
            response_hash=response_hash,
        )
    
    async def log_escalation_trace(
        self,
        session_id: str,
        request_id: str,
        request_preview: Optional[str] = None,
        cycle_detected: bool = False,
        cycle_hash_distance: Optional[float] = None,
        cycle_repetition_count: Optional[int] = None,
        cache_hit: bool = False,
        cache_confidence: Optional[float] = None,
        cache_recommendation: Optional[str] = None,
        cache_weak_calls: int = 0,
        cache_strong_calls: int = 0,
        judge_invoked: bool = False,
        judge_complexity_score: Optional[float] = None,
        judge_impact_scope: Optional[str] = None,
        judge_reasoning: Optional[str] = None,
        judge_latency_ms: Optional[float] = None,
        initial_route_decision: str = "weak",
        final_route_decision: str = "strong",
        escalation_reason: Optional[str] = None,
        model_used: Optional[str] = None,
    ) -> None:
        """
        Log a detailed escalation trace for strong model escalations.
        """
        await asyncio.to_thread(
            self.audit_logger.log_escalation_trace,
            session_id=session_id,
            request_id=request_id,
            request_preview=request_preview,
            cycle_detected=cycle_detected,
            cycle_hash_distance=cycle_hash_distance,
            cycle_repetition_count=cycle_repetition_count,
            cache_hit=cache_hit,
            cache_confidence=cache_confidence,
            cache_recommendation=cache_recommendation,
            cache_weak_calls=cache_weak_calls,
            cache_strong_calls=cache_strong_calls,
            judge_invoked=judge_invoked,
            judge_complexity_score=judge_complexity_score,
            judge_impact_scope=judge_impact_scope,
            judge_reasoning=judge_reasoning,
            judge_latency_ms=judge_latency_ms,
            initial_route_decision=initial_route_decision,
            final_route_decision=final_route_decision,
            escalation_reason=escalation_reason,
            model_used=model_used,
        )

    async def log_threshold_adjustment(
        self,
        old_threshold: float,
        new_threshold: float,
        current_rate: float,
        reason: str,
    ) -> None:
        """
        Log a threshold adjustment.
        """
        logging.info(
            f"Threshold adjusted: {old_threshold:.3f} -> {new_threshold:.3f} "
            f"(current escalation rate: {current_rate:.2%}, reason: {reason})"
        )

    async def log_judge_result(
        self,
        session_id: str,
        complexity_score: float,
        impact_scope: str,
        reasoning: str,
    ) -> None:
        """
        Log a judge categorization result.
        """
        logging.info(
            f"Judge result for session {session_id}: "
            f"complexity={complexity_score:.3f}, impact={impact_scope}, reasoning={reasoning[:100]}..."
        )


# Convenience function for structured logging
def log_structured(level: str, message: str, extra: Dict[str, Any] = None) -> None:
    """
    Log a message with structured extra fields.
    """
    logger = logging.getLogger(__name__)
    extra = extra or {}
    log_method = getattr(logger, level.lower(), logger.info)
    log_method(message, extra=extra)


async def cleanup_old_logs(retention_days: int = 30) -> None:
    """
    Delete log files older than `retention_days`.
    Should be called periodically (e.g., daily).
    """
    logs_dir = get_logs_dir()
    requests_logs_dir = logs_dir / "requests"
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    for log_file in requests_logs_dir.glob("*.json"):
        stat = log_file.stat()
        if datetime.utcfromtimestamp(stat.st_mtime) < cutoff:
            log_file.unlink()
            logging.debug(f"Deleted old log file {log_file}")