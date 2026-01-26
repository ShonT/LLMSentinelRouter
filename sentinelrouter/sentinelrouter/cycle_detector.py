"""
Module D: Graph‑Based Cycle Detection.

Uses SimHash (semantic hash) and networkx to build a directed graph of request‑response
semantic hashes. Detects loops (identical or near‑identical requests within a session) and
blocks repetitive cycles.
"""

import logging
from typing import Optional, List, Tuple, Set
from datetime import datetime, timedelta

try:
    import networkx as nx
except ImportError:
    nx = None  # type: ignore

from .config import get_settings
from .semantic_hash import compute_simhash, hamming_distance

logger = logging.getLogger(__name__)


class CycleDetector:
    """
    Detects cycles in a session's request/response graph using SimHash.

    Requirements:
        - Create Semantic Hash (SimHash) of (User Prompt + Last Assistant Response)
        - Add as node to graph, create edge from previous interaction
        - Detect cycles: if current hash connects to recently visited node (simhash distance < 3)
        - Loop action: Override all logic and route to Strong Model
        - Implement pruning of old nodes (keep last 100 interactions)
    """

    def __init__(
        self,
        session_id: str,
        window_size: int = None,
        simhash_threshold: int = None,
        repetition_threshold: int = 4,
    ):
        settings = get_settings()
        self.session_id = session_id
        self.window_size = (
            window_size
            if window_size is not None
            else settings.cycle_detection_window_size
        )
        self.simhash_threshold = (
            simhash_threshold
            if simhash_threshold is not None
            else settings.cycle_detection_simhash_threshold
        )
        self.repetition_threshold = (
            repetition_threshold  # Only escalate after N repetitions
        )

        if nx is None:
            logger.warning("networkx not installed. Cycle detection will be disabled.")
            self.graph = None
        else:
            self.graph = nx.DiGraph()

        # Keep a sliding window of recent hashes for fast lookup
        self.recent_hashes: List[Tuple[int, datetime]] = []
        # Track only SUCCESSFUL prompts (only added via add_request_response)
        self.successful_prompts: List[
            Tuple[int, datetime]
        ] = []  # Track prompt hashes from successful responses
        self.last_hash: Optional[int] = None
        self.last_response: Optional[str] = None

    def _compute_hash(self, prompt: str, response: str) -> int:
        """
        Compute SimHash of (User Prompt + Last Assistant Response).
        """
        combined = prompt + "\n---\n" + response
        return compute_simhash(combined)

    def add_request_response(
        self, prompt: str, response: str, timestamp: Optional[datetime] = None
    ) -> bool:
        """
        Add a request‑response pair to the graph and check for cycles.

        Returns True if a cycle is detected (simhash distance < threshold), False otherwise.
        """
        current_hash = self._compute_hash(prompt, response)
        ts = timestamp or datetime.utcnow()

        # Check for near‑duplicate with recent hashes
        cycle_detected = self._detect_cycle(current_hash)
        if cycle_detected:
            logger.warning(
                f"Cycle detected in session {self.session_id} "
                f"(hash distance < {self.simhash_threshold}) - current hash: {current_hash}"
            )

        # Add to graph if networkx is available
        if self.graph is not None:
            node_id = str(current_hash)
            self.graph.add_node(node_id, timestamp=ts, hash=current_hash)
            if self.last_hash is not None:
                prev_node = str(self.last_hash)
                self.graph.add_edge(prev_node, node_id, timestamp=ts)
            self.last_hash = current_hash

        # Keep recent hashes for quick lookup
        self.recent_hashes.append((current_hash, ts))
        if len(self.recent_hashes) > self.window_size:
            self.recent_hashes.pop(0)

        # Store the last response for future cycle detection
        self.last_response = response

        # Add this prompt to successful prompts history (only on successful completion)
        prompt_hash = compute_simhash(prompt)
        self.successful_prompts.append((prompt_hash, ts))
        if len(self.successful_prompts) > self.window_size:
            self.successful_prompts.pop(0)

        # Prune old nodes (by count, not time) to keep graph size manageable
        self._prune_by_count()

        return cycle_detected

    def detect_cycle_with_prompt(self, prompt: str) -> bool:
        """
        Detect if the current prompt is very similar to recent SUCCESSFUL prompts,
        indicating a potential repetitive cycle.

        Only escalates if the prompt has been repeated >= repetition_threshold times.
        Only considers prompts from successful requests (tracked via add_request_response).

        Enhanced with two filters:
        1. Only checks last 10 prompts (not entire window of 100)
        2. Only counts prompts from last 15 minutes

        Returns True if a cycle is detected (4+ repetitions), False otherwise.
        """
        # Compute hash of just the prompt (not combined with old response)
        prompt_hash = compute_simhash(prompt)

        # Get current timestamp for time-based filtering
        current_time = datetime.utcnow()
        time_window = timedelta(
            minutes=15
        )  # Only consider prompts from last 15 minutes
        recent_prompt_limit = 10  # Only check last 10 prompts

        # Get recent prompts (last 10) within time window (last 15 minutes)
        recent_prompts = [
            (ph, ts)
            for ph, ts in self.successful_prompts[-recent_prompt_limit:]
            if (current_time - ts) <= time_window
        ]

        # Count how many times this prompt (or similar prompts) appear in recent history
        repetition_count = 0
        for existing_prompt_hash, ts in recent_prompts:
            dist = hamming_distance(prompt_hash, existing_prompt_hash)
            if dist < self.simhash_threshold:
                repetition_count += 1

        # Only escalate if we've seen this prompt 4+ times in recent history
        if repetition_count >= self.repetition_threshold:
            logger.warning(
                f"Cycle detected for session {self.session_id}: "
                f"prompt repeated {repetition_count} times in last {len(recent_prompts)} prompts "
                f"(within 15 min window, threshold={self.repetition_threshold})"
            )
            return True

        logger.debug(
            f"Prompt similarity check for session {self.session_id}: "
            f"{repetition_count} repetitions in last {len(recent_prompts)} prompts "
            f"(threshold={self.repetition_threshold}, no escalation)"
        )
        return False

    def _detect_cycle(self, current_hash: int) -> bool:
        """
        Detect if current hash is similar (distance < threshold) to any recent hash.
        """
        for existing_hash, _ in self.recent_hashes:
            dist = hamming_distance(current_hash, existing_hash)
            if dist < self.simhash_threshold:
                logger.debug(
                    f"Cycle detected: current_hash={current_hash}, "
                    f"existing_hash={existing_hash}, distance={dist}"
                )
                return True
        return False

    def _prune_by_count(self, max_nodes: int = 100):
        """
        Keep only the most recent `max_nodes` in the graph.
        """
        if self.graph is None or self.graph.number_of_nodes() <= max_nodes:
            return

        # Nodes are stored with timestamp attribute; we can sort by timestamp.
        # But we can also rely on recent_hashes order.
        # Simpler: remove nodes not in recent_hashes.
        recent_hash_set = {str(h) for h, _ in self.recent_hashes}
        nodes_to_remove = [n for n in self.graph.nodes() if n not in recent_hash_set]
        for n in nodes_to_remove:
            self.graph.remove_node(n)

        logger.debug(f"Pruned {len(nodes_to_remove)} old nodes from cycle graph.")

    def prune_old_nodes(self, max_age_seconds: int = 3600):
        """
        Remove nodes older than `max_age_seconds` to keep the graph manageable.
        (Alternative pruning by time.)
        """
        if self.graph is None:
            return

        cutoff = datetime.utcnow() - timedelta(seconds=max_age_seconds)
        nodes_to_remove = []
        for node, data in self.graph.nodes(data=True):
            if data.get("timestamp", datetime.utcnow()) < cutoff:
                nodes_to_remove.append(node)

        for node in nodes_to_remove:
            self.graph.remove_node(node)

        # Also prune recent_hashes
        self.recent_hashes = [(h, t) for h, t in self.recent_hashes if t >= cutoff]

        logger.debug(f"Pruned {len(nodes_to_remove)} old nodes from cycle graph.")

    def has_cycle(self) -> bool:
        """
        Public method to check if the current graph contains a directed cycle.
        (Legacy method, kept for compatibility.)
        """
        if self.graph is None:
            return False
        try:
            return bool(list(nx.simple_cycles(self.graph)))
        except nx.NetworkXNoCycle:
            return False

    def find_cycles(self) -> List[List[str]]:
        """
        Return a list of cycles (each cycle is a list of node hashes).
        """
        if self.graph is None:
            return []
        try:
            return list(nx.simple_cycles(self.graph))
        except nx.NetworkXNoCycle:
            return []

    def reset(self):
        """Clear the graph and recent hashes for this session."""
        if self.graph is not None:
            self.graph.clear()
        self.recent_hashes.clear()
        self.successful_prompts.clear()
        self.last_hash = None
        self.last_response = None
        logger.info(f"Cycle detector reset for session {self.session_id}")

    def clear_last_response(self):
        """Clear the last response without resetting the entire detector.
        Used when a request fails to prevent stale response data."""
        self.last_response = None
        logger.debug(f"Cleared last_response for session {self.session_id}")
