"""
Semantic processing module for tiered similarity detection.

Supports three strategies:
- SIMHASH: Ultra-low RAM, heuristic matching
- VECTORDB_LOCAL: <100MB RAM, local embeddings with ONNX
- VECTORDB_API: Gold standard precision, API-based embeddings
"""

from .factory import SemanticProcessorFactory, SemanticStrategy
from .base import SemanticProcessor
from .simhash_processor import SimHashProcessor
from .local_vector_processor import LocalVectorProcessor
from .api_vector_processor import APIVectorProcessor

__all__ = [
    "SemanticProcessorFactory",
    "SemanticStrategy",
    "SemanticProcessor",
    "SimHashProcessor",
    "LocalVectorProcessor",
    "APIVectorProcessor",
]
