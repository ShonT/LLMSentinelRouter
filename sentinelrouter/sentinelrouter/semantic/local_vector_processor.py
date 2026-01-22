"""
Local vector embeddings processor (Mode B: Balanced Default).

Uses ONNX Runtime with all-MiniLM-L6-v2 model.
Memory: ~80MB, Latency: 10-20ms, Good precision for paraphrasing.
"""

import logging
import os
from pathlib import Path
from typing import Union, Optional
import numpy as np

from .base import SemanticProcessor

logger = logging.getLogger(__name__)

# Lazy imports for optional dependencies
onnxruntime = None
AutoTokenizer = None


class LocalVectorProcessor(SemanticProcessor):
    """
    Local vector embeddings using ONNX Runtime.
    
    Memory: ~80MB (45MB model + 30MB runtime + overhead)
    Latency: 10-20ms per embedding on CPU
    Precision: Good (handles paraphrasing better than SimHash)
    
    Model: sentence-transformers/all-MiniLM-L6-v2 (quantized to ONNX)
    """

    def __init__(self, model_path: Optional[str] = None, similarity_threshold: float = 0.85):
        """
        Initialize local vector processor.
        
        Args:
            model_path: Path to ONNX model file (auto-downloads if not found)
            similarity_threshold: Cosine similarity threshold for matching
        """
        global onnxruntime, AutoTokenizer
        
        self.similarity_threshold = similarity_threshold
        self.model_path = model_path or self._get_default_model_path()
        self.session: Optional[object] = None
        self.tokenizer: Optional[object] = None
        
        # Lazy initialization - only load model when first used
        self._initialized = False
        
        logger.info(f"LocalVectorProcessor configured (threshold={similarity_threshold})")

    def _get_default_model_path(self) -> str:
        """Get default path for ONNX model."""
        # Store in data directory alongside database
        base_dir = Path(__file__).parent.parent.parent.parent / "data" / "models"
        base_dir.mkdir(parents=True, exist_ok=True)
        return str(base_dir / "minilm-l6-v2-quantized.onnx")

    async def _ensure_initialized(self):
        """Lazy initialization of ONNX model and tokenizer."""
        if self._initialized:
            return

        global onnxruntime, AutoTokenizer
        
        try:
            # Import dependencies
            if onnxruntime is None:
                import onnxruntime as ort
                onnxruntime = ort
            if AutoTokenizer is None:
                from transformers import AutoTokenizer as AT
                AutoTokenizer = AT
                
            # Download/load model if needed
            if not os.path.exists(self.model_path):
                logger.info("ONNX model not found, downloading...")
                await self._download_model()
            
            # Initialize ONNX session
            self.session = onnxruntime.InferenceSession(
                self.model_path,
                providers=['CPUExecutionProvider']
            )
            
            # Load tokenizer (from HuggingFace)
            self.tokenizer = AutoTokenizer.from_pretrained('sentence-transformers/all-MiniLM-L6-v2')
            
            self._initialized = True
            logger.info("LocalVectorProcessor initialized successfully")
            
        except ImportError as e:
            logger.error(
                f"Failed to import dependencies for LocalVectorProcessor: {e}\n"
                "Install with: pip install onnxruntime transformers"
            )
            raise
        except Exception as e:
            logger.error(f"Failed to initialize LocalVectorProcessor: {e}")
            raise

    async def _download_model(self):
        """
        Download and convert MiniLM model to ONNX format.
        
        Note: In production, pre-convert the model and include it in deployment.
        """
        try:
            from optimum.onnxruntime import ORTModelForFeatureExtraction
            
            logger.info("Downloading and converting all-MiniLM-L6-v2 to ONNX...")
            
            # Load and export to ONNX
            model = ORTModelForFeatureExtraction.from_pretrained(
                'sentence-transformers/all-MiniLM-L6-v2',
                export=True
            )
            
            # Save to configured path
            model.save_pretrained(Path(self.model_path).parent)
            
            # Rename to expected filename
            onnx_file = Path(self.model_path).parent / "model.onnx"
            if onnx_file.exists():
                onnx_file.rename(self.model_path)
                
            logger.info(f"Model saved to {self.model_path}")
            
        except ImportError:
            logger.error(
                "optimum library required for model conversion. "
                "Install with: pip install optimum[onnxruntime]"
            )
            raise
        except Exception as e:
            logger.error(f"Failed to download model: {e}")
            raise

    def _mean_pooling(self, model_output, attention_mask):
        """Apply mean pooling to get sentence embedding."""
        token_embeddings = model_output[0]
        input_mask_expanded = np.broadcast_to(
            attention_mask[:, :, np.newaxis],
            token_embeddings.shape
        ).astype(float)
        return np.sum(token_embeddings * input_mask_expanded, axis=1) / np.clip(
            input_mask_expanded.sum(axis=1), a_min=1e-9, a_max=None
        )

    async def get_embedding(self, text: str) -> np.ndarray:
        """Generate vector embedding for text."""
        await self._ensure_initialized()
        
        # Tokenize
        encoded = self.tokenizer(
            text,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors='np'
        )
        
        # Run inference
        outputs = self.session.run(
            None,
            {
                'input_ids': encoded['input_ids'].astype(np.int64),
                'attention_mask': encoded['attention_mask'].astype(np.int64)
            }
        )
        
        # Mean pooling
        embedding = self._mean_pooling(outputs, encoded['attention_mask'])
        
        # Normalize
        embedding = embedding / np.linalg.norm(embedding, axis=1, keepdims=True)
        
        return embedding[0]

    async def similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Compute cosine similarity between two embeddings.
        
        Returns value between -1.0 and 1.0 (typically 0.0 to 1.0 for semantic similarity).
        """
        # Ensure 1D arrays
        if embedding1.ndim > 1:
            embedding1 = embedding1.flatten()
        if embedding2.ndim > 1:
            embedding2 = embedding2.flatten()
        
        # Cosine similarity
        similarity = np.dot(embedding1, embedding2) / (
            np.linalg.norm(embedding1) * np.linalg.norm(embedding2)
        )
        
        return float(similarity)

    async def is_similar(self, text1: str, text2: str, threshold: float = None) -> bool:
        """Check if two texts are semantically similar."""
        if threshold is None:
            threshold = self.similarity_threshold
        
        emb1 = await self.get_embedding(text1)
        emb2 = await self.get_embedding(text2)
        
        sim = await self.similarity(emb1, emb2)
        
        is_sim = sim >= threshold
        
        if is_sim:
            logger.debug(f"Vector similarity match: {sim:.3f} >= {threshold:.3f}")
        
        return is_sim

    def get_memory_usage_mb(self) -> float:
        """Return approximate memory usage."""
        if not self._initialized:
            return 0.0
        return 80.0  # ~45MB model + ~30MB runtime + ~5MB overhead
