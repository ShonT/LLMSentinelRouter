"""
API-based vector embeddings processor (Mode C: Gold Standard).

Uses external embedding APIs (OpenAI, Anthropic Voyage) for highest precision.
Memory: ~5MB, Latency: 200ms+, Best precision for complex paraphrasing.
"""

import logging
from typing import Union, Optional
import numpy as np
import httpx

from .base import SemanticProcessor

logger = logging.getLogger(__name__)


class APIVectorProcessor(SemanticProcessor):
    """
    API-based vector embeddings using OpenAI or Anthropic.
    
    Memory: ~5MB (just HTTP client)
    Latency: 200ms+ (network dependent)
    Precision: Highest (gold standard for complex paraphrasing)
    Cost: ~$0.00002 per request
    
    Supported APIs:
    - OpenAI: text-embedding-3-small (1536 dimensions, $0.00002/1K tokens)
    - Voyage AI: voyage-2 (1024 dimensions, similar pricing)
    """

    def __init__(
        self,
        api_key: str,
        provider: str = "openai",
        model: str = "text-embedding-3-small",
        similarity_threshold: float = 0.85
    ):
        """
        Initialize API vector processor.
        
        Args:
            api_key: API key for embedding provider
            provider: "openai" or "voyage"
            model: Model name (default: text-embedding-3-small)
            similarity_threshold: Cosine similarity threshold
        """
        self.api_key = api_key
        self.provider = provider.lower()
        self.model = model
        self.similarity_threshold = similarity_threshold
        
        # Set API endpoint
        if self.provider == "openai":
            self.base_url = "https://api.openai.com/v1"
            self.endpoint = f"{self.base_url}/embeddings"
        elif self.provider == "voyage":
            self.base_url = "https://api.voyageai.com/v1"
            self.endpoint = f"{self.base_url}/embeddings"
        else:
            raise ValueError(f"Unsupported provider: {provider}")
        
        # HTTP client for API calls
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
        )
        
        logger.info(f"APIVectorProcessor initialized (provider={provider}, model={model})")

    async def _call_embedding_api(self, text: str) -> np.ndarray:
        """Call external embedding API."""
        try:
            if self.provider == "openai":
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "input": text,
                    "model": self.model
                }
            elif self.provider == "voyage":
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "input": [text],
                    "model": self.model
                }
            else:
                raise ValueError(f"Unknown provider: {self.provider}")
            
            response = await self.client.post(
                self.endpoint,
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Extract embedding
            if self.provider == "openai":
                embedding = data["data"][0]["embedding"]
            elif self.provider == "voyage":
                embedding = data["data"][0]["embedding"]
            
            return np.array(embedding, dtype=np.float32)
            
        except httpx.HTTPStatusError as e:
            logger.error(f"API embedding request failed: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Failed to get API embedding: {e}")
            raise

    async def get_embedding(self, text: str) -> np.ndarray:
        """Generate vector embedding via API."""
        return await self._call_embedding_api(text)

    async def similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """Compute cosine similarity between two embeddings."""
        # Ensure 1D arrays
        if embedding1.ndim > 1:
            embedding1 = embedding1.flatten()
        if embedding2.ndim > 1:
            embedding2 = embedding2.flatten()
        
        # Normalize
        emb1_norm = embedding1 / np.linalg.norm(embedding1)
        emb2_norm = embedding2 / np.linalg.norm(embedding2)
        
        # Cosine similarity
        similarity = float(np.dot(emb1_norm, emb2_norm))
        
        return similarity

    async def is_similar(self, text1: str, text2: str, threshold: float = None) -> bool:
        """Check if two texts are semantically similar."""
        if threshold is None:
            threshold = self.similarity_threshold
        
        emb1 = await self.get_embedding(text1)
        emb2 = await self.get_embedding(text2)
        
        sim = await self.similarity(emb1, emb2)
        
        is_sim = sim >= threshold
        
        if is_sim:
            logger.debug(f"API vector similarity match: {sim:.3f} >= {threshold:.3f}")
        
        return is_sim

    def get_memory_usage_mb(self) -> float:
        """Return approximate memory usage."""
        return 5.0  # Just HTTP client overhead

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
