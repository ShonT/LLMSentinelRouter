"""
SimHash-based semantic processor (Mode A: Baseline).

Ultra-low RAM usage (~1-5MB), heuristic matching.
Best for: Quick duplicate detection, low memory environments.
"""

import re
import logging
from typing import Union
import numpy as np

from .base import SemanticProcessor
from ..semantic_hash import compute_simhash, hamming_distance

logger = logging.getLogger(__name__)


class SimHashProcessor(SemanticProcessor):
    """
    SimHash-based similarity detection.

    Memory: ~1-5MB
    Latency: <1ms per operation
    Precision: Good for exact/near duplicates, poor for paraphrasing
    """

    def __init__(self, hash_bits: int = 64, hamming_threshold: int = 3):
        """
        Initialize SimHash processor.

        Args:
            hash_bits: Number of bits for SimHash (default: 64)
            hamming_threshold: Maximum hamming distance for "similar" (default: 3)
        """
        self.hash_bits = hash_bits
        self.hamming_threshold = hamming_threshold
        logger.info(
            f"Initialized SimHashProcessor (hash_bits={hash_bits}, threshold={hamming_threshold})"
        )

    def _normalize_text(self, text: str) -> str:
        """
        Normalize text before hashing to improve robustness.

        Production fix: lowercase, strip whitespace, remove punctuation.
        """
        # Lowercase
        text = text.lower()
        # Remove extra whitespace
        text = re.sub(r"\s+", " ", text).strip()
        # Remove most punctuation (keep apostrophes for contractions)
        text = re.sub(r"[^\w\s\']", "", text)
        return text

    async def get_embedding(self, text: str) -> int:
        """Generate SimHash for text."""
        normalized = self._normalize_text(text)
        hash_value = compute_simhash(normalized, self.hash_bits)
        return hash_value

    async def similarity(self, embedding1: int, embedding2: int) -> float:
        """
        Compute similarity between two SimHashes.

        Returns normalized similarity score (0.0 to 1.0) based on hamming distance.
        """
        distance = hamming_distance(embedding1, embedding2, self.hash_bits)
        # Normalize: 0 distance = 1.0 similarity, max distance (hash_bits) = 0.0 similarity
        similarity = 1.0 - (distance / self.hash_bits)
        return similarity

    async def is_similar(self, text1: str, text2: str, threshold: float = 0.85) -> bool:
        """
        Check if two texts are similar using SimHash.

        For SimHash, threshold is converted to hamming distance.
        Default threshold 0.85 maps to ~10 bit differences for 64-bit hash.
        """
        hash1 = await self.get_embedding(text1)
        hash2 = await self.get_embedding(text2)

        distance = hamming_distance(hash1, hash2, self.hash_bits)

        # Use hamming_threshold if provided, otherwise derive from similarity threshold
        max_distance = int((1.0 - threshold) * self.hash_bits)
        max_distance = min(max_distance, self.hamming_threshold)

        is_sim = distance <= max_distance

        if is_sim:
            logger.debug(
                f"SimHash match: distance={distance}, threshold={max_distance}"
            )

        return is_sim

    def get_memory_usage_mb(self) -> float:
        """Return approximate memory usage."""
        return 0.005  # Negligible ~5KB
