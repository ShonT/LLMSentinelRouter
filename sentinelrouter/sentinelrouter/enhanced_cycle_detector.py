"""
Enhanced cycle detector with pluggable semantic processing.

Supports three modes:
- SIMHASH: Original implementation (backward compatible)
- VECTORDB_LOCAL: Local embeddings for better paraphrase detection
- VECTORDB_API: API-based embeddings for highest accuracy
"""

import logging
from typing import Optional, List, Tuple
from datetime import datetime, timedelta

try:
    import networkx as nx
except ImportError:
    nx = None  # type: ignore

from .config import get_settings
from .semantic.factory import SemanticProcessorFactory, SemanticStrategy
from .semantic.base import SemanticProcessor
from .semantic.vector_store import VectorStore

logger = logging.getLogger(__name__)


class EnhancedCycleDetector:
    """
    Enhanced cycle detector with pluggable semantic processing strategies.
    
    Backward compatible with original CycleDetector but adds:
    - Configurable semantic strategies (SimHash, Local Vectors, API Vectors)
    - Better paraphrase detection with vector embeddings
    - Optional persistent storage with LanceDB
    """

    def __init__(
        self,
        session_id: str,
        window_size: int = None,
        similarity_threshold: float = None,
        repetition_threshold: int = 4,
        semantic_processor: Optional[SemanticProcessor] = None,
        enable_storage: bool = False
    ):
        """
        Initialize enhanced cycle detector.
        
        Args:
            session_id: Session identifier
            window_size: Number of recent interactions to keep
            similarity_threshold: Threshold for semantic similarity (0.0 to 1.0)
            repetition_threshold: Number of repetitions before escalating
            semantic_processor: Custom semantic processor (auto-created if None)
            enable_storage: Whether to use persistent vector storage
        """
        settings = get_settings()
        
        self.session_id = session_id
        self.window_size = window_size if window_size is not None else settings.cycle_detection_window_size
        self.similarity_threshold = similarity_threshold if similarity_threshold is not None else settings.semantic_similarity_threshold
        self.repetition_threshold = repetition_threshold
        
        # Initialize semantic processor
        if semantic_processor is None:
            self.semantic_processor = SemanticProcessorFactory.from_settings(settings)
        else:
            self.semantic_processor = semantic_processor
        
        logger.info(
            f"EnhancedCycleDetector initialized for session {session_id} "
            f"(processor={type(self.semantic_processor).__name__}, "
            f"threshold={self.similarity_threshold})"
        )
        
        # Optional vector storage
        self.enable_storage = enable_storage
        self.vector_store: Optional[VectorStore] = None
        if enable_storage:
            self.vector_store = VectorStore(
                storage_path=f"data/vectors/{session_id}",
                use_lancedb=True
            )
        
        # Graph for cycle detection (optional, if networkx available)
        if nx is None:
            logger.warning("networkx not installed. Graph visualization will be disabled.")
            self.graph = None
        else:
            self.graph = nx.DiGraph()
        
        # In-memory tracking
        self.recent_prompts: List[Tuple[object, datetime]] = []  # (embedding, timestamp)
        self.recent_interactions: List[Tuple[object, datetime]] = []  # (prompt+response embedding, timestamp)
        self.last_embedding: Optional[object] = None
        self.last_response: Optional[str] = None

    async def add_request_response(
        self,
        prompt: str,
        response: str,
        timestamp: Optional[datetime] = None
    ) -> bool:
        """
        Add a request-response pair and check for cycles.
        
        Args:
            prompt: User prompt
            response: Assistant response
            timestamp: Optional timestamp (defaults to now)
            
        Returns:
            True if cycle detected, False otherwise
        """
        ts = timestamp or datetime.utcnow()
        
        # Generate embedding for combined prompt+response
        combined = prompt + "\n---\n" + response
        interaction_embedding = await self.semantic_processor.get_embedding(combined)
        
        # Check for cycles in interactions
        cycle_detected = await self._detect_cycle(interaction_embedding)
        
        if cycle_detected:
            logger.warning(
                f"Cycle detected in session {self.session_id} "
                f"(similarity >= {self.similarity_threshold})"
            )
        
        # Store in vector store if enabled
        if self.vector_store:
            await self.vector_store.add_embedding(
                session_id=self.session_id,
                text=combined,
                embedding=interaction_embedding,
                metadata={"type": "interaction", "timestamp": ts.isoformat()}
            )
        
        # Update graph
        if self.graph is not None:
            node_id = f"{self.session_id}_{ts.isoformat()}"
            self.graph.add_node(node_id, timestamp=ts, embedding=interaction_embedding)
            if self.last_embedding is not None:
                prev_node = f"{self.session_id}_{ts.isoformat()}"
                self.graph.add_edge(prev_node, node_id, timestamp=ts)
            self.last_embedding = interaction_embedding
        
        # Keep recent interactions
        self.recent_interactions.append((interaction_embedding, ts))
        if len(self.recent_interactions) > self.window_size:
            self.recent_interactions.pop(0)
        
        # Track successful prompts
        prompt_embedding = await self.semantic_processor.get_embedding(prompt)
        self.recent_prompts.append((prompt_embedding, ts))
        if len(self.recent_prompts) > self.window_size:
            self.recent_prompts.pop(0)
        
        self.last_response = response
        
        return cycle_detected

    async def detect_cycle_with_prompt(self, prompt: str) -> bool:
        """
        Detect if the current prompt is very similar to recent successful prompts.
        
        Uses semantic similarity to detect paraphrases and near-duplicates.
        
        Args:
            prompt: User prompt to check
            
        Returns:
            True if cycle detected (repetition >= threshold), False otherwise
        """
        prompt_embedding = await self.semantic_processor.get_embedding(prompt)
        
        # Time-based filtering: only check last 15 minutes
        current_time = datetime.utcnow()
        time_window = timedelta(minutes=15)
        recent_prompt_limit = 10  # Only check last 10 prompts
        
        # Get recent prompts
        recent_prompts = [
            (emb, ts) for emb, ts in self.recent_prompts[-recent_prompt_limit:]
            if (current_time - ts) <= time_window
        ]
        
        if not recent_prompts:
            return False
        
        # Count similar prompts
        repetition_count = 0
        for existing_embedding, ts in recent_prompts:
            similarity = await self.semantic_processor.similarity(prompt_embedding, existing_embedding)
            
            if similarity >= self.similarity_threshold:
                repetition_count += 1
                logger.debug(
                    f"Similar prompt found: similarity={similarity:.3f} "
                    f"(threshold={self.similarity_threshold})"
                )
        
        # Escalate if threshold exceeded
        if repetition_count >= self.repetition_threshold:
            logger.warning(
                f"Cycle detected for session {self.session_id}: "
                f"prompt repeated {repetition_count} times in last {len(recent_prompts)} prompts "
                f"(within 15 min window, threshold={self.repetition_threshold})"
            )
            return True
        
        return False

    async def _detect_cycle(self, embedding: object) -> bool:
        """
        Check if embedding is similar to recent interactions.
        
        Args:
            embedding: Current interaction embedding
            
        Returns:
            True if similar interaction found
        """
        if not self.recent_interactions:
            return False
        
        # Check against recent interactions
        for existing_embedding, ts in self.recent_interactions[-10:]:  # Last 10 interactions
            similarity = await self.semantic_processor.similarity(embedding, existing_embedding)
            
            if similarity >= self.similarity_threshold:
                logger.debug(f"Cycle match: similarity={similarity:.3f}")
                return True
        
        return False

    async def is_similar_to_recent(self, prompt: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """
        Find most similar recent prompts (for analysis/debugging).
        
        Args:
            prompt: Query prompt
            top_k: Number of similar prompts to return
            
        Returns:
            List of (prompt_text, similarity_score) tuples
        """
        if not self.vector_store:
            return []
        
        prompt_embedding = await self.semantic_processor.get_embedding(prompt)
        
        results = await self.vector_store.search_similar(
            embedding=prompt_embedding,
            session_id=self.session_id,
            top_k=top_k,
            similarity_threshold=0.0  # Get all, we'll sort by score
        )
        
        return [(text, score) for text, score, _ in results]

    def get_memory_usage_mb(self) -> float:
        """Return approximate memory usage."""
        processor_mem = self.semantic_processor.get_memory_usage_mb()
        storage_mem = self.vector_store.get_memory_usage_mb() if self.vector_store else 0.0
        graph_mem = 5.0 if self.graph else 0.0  # networkx graph overhead
        
        return processor_mem + storage_mem + graph_mem

    async def close(self):
        """Clean up resources."""
        if self.vector_store:
            await self.vector_store.close()
        
        # Close API clients if using API processor
        if hasattr(self.semantic_processor, 'close'):
            await self.semantic_processor.close()
