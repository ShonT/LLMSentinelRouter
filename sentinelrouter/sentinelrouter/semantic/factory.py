"""
Factory for creating semantic processors based on configuration.
"""

import logging
from enum import Enum
from typing import Optional

from .base import SemanticProcessor
from .simhash_processor import SimHashProcessor
from .local_vector_processor import LocalVectorProcessor
from .api_vector_processor import APIVectorProcessor

logger = logging.getLogger(__name__)


class SemanticStrategy(str, Enum):
    """Semantic similarity detection strategy."""
    SIMHASH = "SIMHASH"                 # Ultra-low RAM, heuristic matching
    VECTORDB_LOCAL = "VECTORDB_LOCAL"   # <100MB RAM, local embeddings (Default)
    VECTORDB_API = "VECTORDB_API"       # Gold standard precision, API-based


class SemanticProcessorFactory:
    """Factory for creating semantic processors."""

    @staticmethod
    def create(
        strategy: SemanticStrategy,
        similarity_threshold: float = 0.85,
        api_key: Optional[str] = None,
        model_path: Optional[str] = None,
        **kwargs
    ) -> SemanticProcessor:
        """
        Create a semantic processor based on strategy.
        
        Args:
            strategy: Which strategy to use (SIMHASH, VECTORDB_LOCAL, VECTORDB_API)
            similarity_threshold: Similarity threshold for matching (0.0 to 1.0)
            api_key: API key for VECTORDB_API strategy
            model_path: Custom model path for VECTORDB_LOCAL
            **kwargs: Additional strategy-specific arguments
            
        Returns:
            Initialized SemanticProcessor
            
        Examples:
            # Ultra-fast SimHash
            processor = SemanticProcessorFactory.create(SemanticStrategy.SIMHASH)
            
            # Balanced local vectors
            processor = SemanticProcessorFactory.create(
                SemanticStrategy.VECTORDB_LOCAL,
                similarity_threshold=0.90
            )
            
            # High-precision API
            processor = SemanticProcessorFactory.create(
                SemanticStrategy.VECTORDB_API,
                api_key="sk-..."
            )
        """
        logger.info(f"Creating semantic processor: {strategy}")
        
        if strategy == SemanticStrategy.SIMHASH:
            # Mode A: SimHash (baseline)
            hamming_threshold = kwargs.get('hamming_threshold', 3)
            hash_bits = kwargs.get('hash_bits', 64)
            
            return SimHashProcessor(
                hash_bits=hash_bits,
                hamming_threshold=hamming_threshold
            )
        
        elif strategy == SemanticStrategy.VECTORDB_LOCAL:
            # Mode B: Local vectors with ONNX (default)
            return LocalVectorProcessor(
                model_path=model_path,
                similarity_threshold=similarity_threshold
            )
        
        elif strategy == SemanticStrategy.VECTORDB_API:
            # Mode C: API-based vectors (gold standard)
            if not api_key:
                raise ValueError("api_key required for VECTORDB_API strategy")
            
            provider = kwargs.get('provider', 'openai')
            model = kwargs.get('model', 'text-embedding-3-small')
            
            return APIVectorProcessor(
                api_key=api_key,
                provider=provider,
                model=model,
                similarity_threshold=similarity_threshold
            )
        
        else:
            raise ValueError(f"Unknown semantic strategy: {strategy}")

    @staticmethod
    def from_settings(settings) -> SemanticProcessor:
        """
        Create processor from application settings.
        
        Args:
            settings: Application Settings object
            
        Returns:
            Configured SemanticProcessor
        """
        strategy_str = getattr(settings, 'semantic_strategy', 'VECTORDB_LOCAL').upper()
        
        try:
            strategy = SemanticStrategy(strategy_str)
        except ValueError:
            logger.warning(f"Invalid semantic strategy '{strategy_str}', defaulting to VECTORDB_LOCAL")
            strategy = SemanticStrategy.VECTORDB_LOCAL
        
        similarity_threshold = getattr(settings, 'semantic_similarity_threshold', 0.85)
        
        # Get strategy-specific settings
        kwargs = {}
        
        if strategy == SemanticStrategy.SIMHASH:
            kwargs['hamming_threshold'] = getattr(settings, 'cycle_detection_simhash_threshold', 3)
            kwargs['hash_bits'] = getattr(settings, 'semantic_hash_bits', 64)
        
        elif strategy == SemanticStrategy.VECTORDB_LOCAL:
            model_path = getattr(settings, 'semantic_model_path', None)
            kwargs['model_path'] = model_path
        
        elif strategy == SemanticStrategy.VECTORDB_API:
            api_key = getattr(settings, 'semantic_api_key', None) or \
                      getattr(settings, 'openai_api_key', None)
            
            if not api_key:
                logger.warning("No API key found for VECTORDB_API, falling back to VECTORDB_LOCAL")
                strategy = SemanticStrategy.VECTORDB_LOCAL
            else:
                kwargs['api_key'] = api_key
                kwargs['provider'] = getattr(settings, 'semantic_api_provider', 'openai')
                kwargs['model'] = getattr(settings, 'semantic_api_model', 'text-embedding-3-small')
        
        return SemanticProcessorFactory.create(
            strategy=strategy,
            similarity_threshold=similarity_threshold,
            **kwargs
        )
