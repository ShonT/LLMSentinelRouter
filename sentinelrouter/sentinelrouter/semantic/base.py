"""
Base interface for semantic processors.
"""

from abc import ABC, abstractmethod
from typing import Union, List
import numpy as np


class SemanticProcessor(ABC):
    """Abstract base class for semantic similarity detection."""

    @abstractmethod
    async def get_embedding(self, text: str) -> Union[int, np.ndarray]:
        """
        Generate an embedding for the given text.

        Returns:
            - int for SimHash (64-bit hash)
            - np.ndarray for vector embeddings (384-dim for MiniLM, 1536-dim for OpenAI)
        """
        pass

    @abstractmethod
    async def similarity(
        self, embedding1: Union[int, np.ndarray], embedding2: Union[int, np.ndarray]
    ) -> float:
        """
        Compute similarity between two embeddings.

        Returns:
            Float between 0.0 (completely different) and 1.0 (identical)
        """
        pass

    @abstractmethod
    async def is_similar(self, text1: str, text2: str, threshold: float = 0.85) -> bool:
        """
        Check if two texts are semantically similar above a threshold.

        Args:
            text1: First text
            text2: Second text
            threshold: Similarity threshold (0.0 to 1.0)

        Returns:
            True if similarity >= threshold
        """
        pass

    @abstractmethod
    def get_memory_usage_mb(self) -> float:
        """Return approximate memory usage in MB."""
        pass
