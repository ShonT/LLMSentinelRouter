"""
Metrics collection and persistence module for SentinelRouter.

Tracks:
- Judge latency
- Model latency (weak/strong)
- Fallback occurrences
- Cycle detection
- Tokens per second

Persists metrics to file storage with 200MB limit.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
import logging
from collections import deque
from threading import Lock

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    Collects and persists metrics to file storage.
    
    Features:
    - File-based persistence with 200MB limit
    - Auto-rotation when limit exceeded
    - Thread-safe operations
    - JSON format for easy parsing
    """
    
    def __init__(self, storage_dir: str = "./data/metrics", max_size_mb: int = 200):
        self.storage_dir = Path(storage_dir)
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self.metrics_file = self.storage_dir / "metrics.jsonl"
        self.lock = Lock()
        
        # In-memory buffer for recent metrics (for dashboard)
        self.recent_metrics = deque(maxlen=1000)  # Keep last 1000 metrics
        
        # Load existing metrics from file
        self._load_recent_metrics()
        
        logger.info(f"MetricsCollector initialized: {self.storage_dir}, max_size={max_size_mb}MB, loaded {len(self.recent_metrics)} recent metrics")
    
    def _check_and_rotate_if_needed(self):
        """Check file size and rotate if needed."""
        if not self.metrics_file.exists():
            return
        
        file_size = self.metrics_file.stat().st_size
        if file_size >= self.max_size_bytes:
            logger.warning(f"Metrics file exceeded {self.max_size_bytes} bytes, rotating...")
            
            # Archive old file with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_file = self.storage_dir / f"metrics_archive_{timestamp}.jsonl"
            self.metrics_file.rename(archive_file)
            
            # Remove oldest archives if total size exceeds limit
            self._cleanup_old_archives()
            
            logger.info(f"Metrics rotated to {archive_file}")
    
    def _cleanup_old_archives(self):
        """Remove oldest archive files if total size exceeds limit."""
        archives = sorted(self.storage_dir.glob("metrics_archive_*.jsonl"))
        total_size = sum(f.stat().st_size for f in archives)
        
        # Keep removing oldest until under limit
        while total_size > self.max_size_bytes and archives:
            oldest = archives.pop(0)
            removed_size = oldest.stat().st_size
            oldest.unlink()
            total_size -= removed_size
            logger.info(f"Removed old archive: {oldest.name}")
    
    def _load_recent_metrics(self):
        """Load recent metrics from file into in-memory buffer."""
        if not self.metrics_file.exists():
            logger.info("No existing metrics file found, starting fresh")
            self.recent_metrics.clear()
            return
        
        try:
            # Clear existing buffer first
            self.recent_metrics.clear()
            
            with open(self.metrics_file, "r") as f:
                # Read last 1000 lines efficiently
                lines = deque(f, maxlen=1000)
                
            for line in lines:
                try:
                    metric = json.loads(line.strip())
                    self.recent_metrics.append(metric)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse metric line: {e}")
                    
            logger.info(f"Loaded {len(self.recent_metrics)} metrics from file")
        except Exception as e:
            logger.error(f"Failed to load metrics from file: {e}")
    
    def record_judge_latency(self, judge_id: str, latency_ms: float, status: str):
        """Record judge latency."""
        metric = {
            "type": "judge_latency",
            "timestamp": time.time(),
            "judge_id": judge_id,
            "latency_ms": latency_ms,
            "status": status
        }
        self._write_metric(metric)
    
    def record_model_latency(self, model_id: str, route_type: str, latency_ms: float, status: str):
        """Record model latency (weak or strong)."""
        metric = {
            "type": f"{route_type}_model_latency",
            "timestamp": time.time(),
            "model_id": model_id,
            "route_type": route_type,
            "latency_ms": latency_ms,
            "status": status
        }
        self._write_metric(metric)
    
    def record_fallback(self, fallback_type: str, primary_id: str, backup_id: str):
        """Record fallback occurrence."""
        metric = {
            "type": f"{fallback_type}_fallback",
            "timestamp": time.time(),
            "primary_id": primary_id,
            "backup_id": backup_id
        }
        self._write_metric(metric)
    
    def record_cycle_detection(self, session_id: str, hash_distance: int):
        """Record cycle detection."""
        metric = {
            "type": "cycle_detection",
            "timestamp": time.time(),
            "session_id": session_id,
            "hash_distance": hash_distance
        }
        self._write_metric(metric)
    
    def record_tokens_per_second(self, model_id: str, route_type: str, tps: float, total_tokens: int):
        """Record tokens per second."""
        metric = {
            "type": "tokens_per_second",
            "timestamp": time.time(),
            "model_id": model_id,
            "route_type": route_type,
            "tps": tps,
            "total_tokens": total_tokens
        }
        self._write_metric(metric)

    def record_semantic_cache_event(self, event: str, semantic_hash: str, hit: bool, confidence: float):
        """Record semantic cache lookup/record events."""
        metric = {
            "type": "semantic_cache",
            "timestamp": time.time(),
            "event": event,
            "semantic_hash": semantic_hash,
            "hit": hit,
            "confidence": confidence,
        }
        self._write_metric(metric)

    def record_judge_timeout_escalation(self, session_id: str, model_id: str, timeout_ms: float):
        """Record when a weak model times out and judge is called for escalation."""
        metric = {
            "type": "judge_timeout_escalation",
            "timestamp": time.time(),
            "session_id": session_id,
            "model_id": model_id,
            "timeout_ms": timeout_ms,
        }
        self._write_metric(metric)
    
    def record_judge_skip(self, session_id: str, reason: str):
        """Record when judge is skipped (use_judge=false or conditional mode)."""
        metric = {
            "type": "judge_skip",
            "timestamp": time.time(),
            "session_id": session_id,
            "reason": reason,
        }
        self._write_metric(metric)

    def record_strong_model_usage(
        self, 
        model_id: str, 
        reason: str, 
        complexity_score: float = None,
        impact_scope: str = None,
        threshold: float = None,
        cycle_detected: bool = False,
        cycle_history: List[str] = None,
        request_preview: str = None,
        response_preview: str = None,
        session_id: str = None
    ):
        """Record strong model usage with detailed reasoning."""
        metric = {
            "type": "strong_model_usage",
            "timestamp": time.time(),
            "model_id": model_id,
            "reason": reason,
            "session_id": session_id,
        }
        
        # Add complexity info if available
        if complexity_score is not None:
            metric["complexity_score"] = complexity_score
            metric["threshold"] = threshold
            metric["impact_scope"] = impact_scope
        
        # Add cycle info if detected
        if cycle_detected:
            metric["cycle_detected"] = True
            if cycle_history:
                metric["cycle_history"] = cycle_history
        
        # Add request/response previews (truncated for storage)
        if request_preview:
            metric["request_preview"] = request_preview[:500]  # First 500 chars
        if response_preview:
            metric["response_preview"] = response_preview[:500]  # First 500 chars
        
        self._write_metric(metric)
    
    def _write_metric(self, metric: Dict[str, Any]):
        """Write metric to file and in-memory buffer."""
        with self.lock:
            # Add to in-memory buffer
            self.recent_metrics.append(metric)
            
            # Check and rotate if needed
            self._check_and_rotate_if_needed()
            
            # Write to file
            with open(self.metrics_file, "a") as f:
                f.write(json.dumps(metric) + "\n")
    
    def get_recent_metrics(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent metrics from in-memory buffer."""
        with self.lock:
            return list(self.recent_metrics)[-limit:]
    
    def get_aggregated_stats(self) -> Dict[str, Any]:
        """Get aggregated statistics from recent metrics."""
        with self.lock:
            metrics = list(self.recent_metrics)
        
        if not metrics:
            return {}
        
        stats = {
            "total_metrics": len(metrics),
            "judge_latency": self._aggregate_latency(metrics, "judge_latency"),
            "weak_model_latency": self._aggregate_latency(metrics, "weak_model_latency"),
            "strong_model_latency": self._aggregate_latency(metrics, "strong_model_latency"),
            "fallback_counts": self._count_fallbacks(metrics),
            "cycle_detection_count": self._count_cycles(metrics),
            "tokens_per_second": self._aggregate_tps(metrics),
            "strong_model_usages": self._get_strong_model_usages(metrics),
            "semantic_cache": self._aggregate_semantic_cache(metrics),
        }

        return stats
    
    def _aggregate_latency(self, metrics: List[Dict], metric_type: str) -> Dict[str, Any]:
        """Aggregate latency metrics."""
        latencies = [m["latency_ms"] for m in metrics if m.get("type") == metric_type]
        if not latencies:
            return {"count": 0, "avg": 0, "min": 0, "max": 0, "p50": 0, "p95": 0, "p99": 0}
        
        latencies.sort()
        count = len(latencies)
        return {
            "count": count,
            "avg": sum(latencies) / count,
            "min": latencies[0],
            "max": latencies[-1],
            "p50": latencies[int(count * 0.5)],
            "p95": latencies[int(count * 0.95)] if count > 1 else latencies[0],
            "p99": latencies[int(count * 0.99)] if count > 1 else latencies[0],
        }
    
    def _count_fallbacks(self, metrics: List[Dict]) -> Dict[str, int]:
        """Count fallback occurrences."""
        fallback_types = ["judge_fallback", "weak_model_fallback", "strong_model_fallback"]
        counts = {}
        for fb_type in fallback_types:
            counts[fb_type] = len([m for m in metrics if m.get("type") == fb_type])
        return counts
    
    def _count_cycles(self, metrics: List[Dict]) -> int:
        """Count cycle detection occurrences."""
        return len([m for m in metrics if m.get("type") == "cycle_detection"])
    
    def _get_strong_model_usages(self, metrics: List[Dict]) -> List[Dict[str, Any]]:
        """Get strong model usage events."""
        return [m for m in metrics if m.get("type") == "strong_model_usage"]
    
    def _aggregate_tps(self, metrics: List[Dict]) -> Dict[str, Any]:
        """Aggregate tokens per second metrics."""
        tps_metrics = [m for m in metrics if m.get("type") == "tokens_per_second"]
        if not tps_metrics:
            return {"count": 0, "avg": 0, "total_tokens": 0}
        
        tps_values = [m["tps"] for m in tps_metrics]
        total_tokens = sum(m["total_tokens"] for m in tps_metrics)
        
        return {
            "count": len(tps_values),
            "avg": sum(tps_values) / len(tps_values),
            "total_tokens": total_tokens,
        }

    def _aggregate_semantic_cache(self, metrics: List[Dict]) -> Dict[str, Any]:
        """Aggregate semantic cache hit/miss information."""
        cache_events = [m for m in metrics if m.get("type") == "semantic_cache"]
        if not cache_events:
            return {"lookups": 0, "hits": 0, "misses": 0, "avg_confidence": 0.0}

        hits = len([m for m in cache_events if m.get("hit")])
        misses = len(cache_events) - hits
        confidences = [m.get("confidence", 0.0) for m in cache_events]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        return {
            "lookups": len(cache_events),
            "hits": hits,
            "misses": misses,
            "avg_confidence": avg_conf,
        }

    def reset_metrics(self):
        """Reset all metrics - clear in-memory buffer and delete metrics file."""
        with self.lock:
            # Clear in-memory buffer
            self.recent_metrics.clear()
            
            # Delete metrics file if it exists
            if self.metrics_file.exists():
                self.metrics_file.unlink()
                logger.info(f"Deleted metrics file: {self.metrics_file}")
            
            # Optionally delete archive files too
            archives = list(self.storage_dir.glob("metrics_archive_*.jsonl"))
            for archive in archives:
                archive.unlink()
                logger.info(f"Deleted archive: {archive.name}")
            
            logger.info("All metrics reset to zero")


# Global metrics collector instance
_metrics_collector: MetricsCollector = None


def get_metrics_collector() -> MetricsCollector:
    """Get or create the global metrics collector."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector
