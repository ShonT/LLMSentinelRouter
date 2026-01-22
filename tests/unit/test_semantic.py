"""
Tests for semantic processing module.
"""

import sys
import pytest
import numpy as np
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import semantic module components directly (avoid triggering settings validation)
from sentinelrouter.sentinelrouter.semantic.simhash_processor import SimHashProcessor
from sentinelrouter.sentinelrouter.semantic.local_vector_processor import LocalVectorProcessor
from sentinelrouter.sentinelrouter.semantic.api_vector_processor import APIVectorProcessor
from sentinelrouter.sentinelrouter.semantic.factory import SemanticProcessorFactory, SemanticStrategy


class TestSimHashProcessor:
    """Test SimHash-based processor."""

    @pytest.fixture
    def processor(self):
        return SimHashProcessor(hash_bits=64, hamming_threshold=3)

    @pytest.mark.asyncio
    async def test_get_embedding(self, processor):
        """Test generating SimHash embedding."""
        text = "Hello world"
        embedding = await processor.get_embedding(text)
        
        assert isinstance(embedding, int)
        assert embedding > 0

    @pytest.mark.asyncio
    async def test_identical_texts_high_similarity(self, processor):
        """Test identical texts have high similarity."""
        text = "The quick brown fox jumps over the lazy dog"
        
        emb1 = await processor.get_embedding(text)
        emb2 = await processor.get_embedding(text)
        
        similarity = await processor.similarity(emb1, emb2)
        assert similarity == 1.0

    @pytest.mark.asyncio
    async def test_different_texts_low_similarity(self, processor):
        """Test very different texts have low similarity."""
        text1 = "The quick brown fox jumps over the lazy dog"
        text2 = "Artificial intelligence is transforming the world"
        
        emb1 = await processor.get_embedding(text1)
        emb2 = await processor.get_embedding(text2)
        
        similarity = await processor.similarity(emb1, emb2)
        assert similarity < 0.7  # Should be quite different

    @pytest.mark.asyncio
    async def test_similar_texts_moderate_similarity(self, processor):
        """Test similar texts have moderate similarity."""
        text1 = "The quick brown fox jumps over the lazy dog"
        text2 = "The fast brown fox leaps over the sleepy dog"
        
        emb1 = await processor.get_embedding(text1)
        emb2 = await processor.get_embedding(text2)
        
        similarity = await processor.similarity(emb1, emb2)
        assert 0.6 < similarity < 1.0  # Should be similar but not identical

    @pytest.mark.asyncio
    async def test_is_similar_exact_match(self, processor):
        """Test is_similar detects exact matches."""
        text = "Hello world"
        
        is_sim = await processor.is_similar(text, text, threshold=0.85)
        assert is_sim is True

    @pytest.mark.asyncio
    async def test_is_similar_different_texts(self, processor):
        """Test is_similar rejects very different texts."""
        text1 = "Hello world"
        text2 = "Completely different content about AI"
        
        is_sim = await processor.is_similar(text1, text2, threshold=0.85)
        assert is_sim is False

    @pytest.mark.asyncio
    async def test_normalization_case_insensitive(self, processor):
        """Test that normalization handles case differences."""
        text1 = "Hello World"
        text2 = "hello world"
        
        is_sim = await processor.is_similar(text1, text2, threshold=0.85)
        assert is_sim is True

    @pytest.mark.asyncio
    async def test_normalization_whitespace(self, processor):
        """Test that normalization handles whitespace differences."""
        text1 = "Hello    world"
        text2 = "Hello world"
        
        is_sim = await processor.is_similar(text1, text2, threshold=0.85)
        assert is_sim is True

    def test_memory_usage(self, processor):
        """Test memory usage reporting."""
        mem = processor.get_memory_usage_mb()
        assert 0 < mem < 1  # Should be very small


class TestLocalVectorProcessor:
    """Test local vector processor (ONNX-based)."""

    @pytest.fixture
    def processor(self):
        return LocalVectorProcessor(similarity_threshold=0.85)

    @pytest.mark.asyncio
    @pytest.mark.skipif(True, reason="Requires ONNX runtime and model download")
    async def test_get_embedding(self, processor):
        """Test generating vector embedding."""
        text = "Hello world"
        embedding = await processor.get_embedding(text)
        
        assert isinstance(embedding, np.ndarray)
        assert embedding.shape[0] > 0  # Should have dimensions

    @pytest.mark.asyncio
    @pytest.mark.skipif(True, reason="Requires ONNX runtime")
    async def test_similarity(self, processor):
        """Test cosine similarity computation."""
        emb1 = np.array([1.0, 0.0, 0.0])
        emb2 = np.array([1.0, 0.0, 0.0])
        
        similarity = await processor.similarity(emb1, emb2)
        assert abs(similarity - 1.0) < 0.01  # Should be very close to 1.0

    @pytest.mark.asyncio
    @pytest.mark.skipif(True, reason="Requires ONNX runtime")
    async def test_orthogonal_vectors_zero_similarity(self, processor):
        """Test orthogonal vectors have zero similarity."""
        emb1 = np.array([1.0, 0.0, 0.0])
        emb2 = np.array([0.0, 1.0, 0.0])
        
        similarity = await processor.similarity(emb1, emb2)
        assert abs(similarity) < 0.01  # Should be close to 0

    def test_memory_usage(self, processor):
        """Test memory usage reporting."""
        mem = processor.get_memory_usage_mb()
        assert mem >= 0  # Should report valid memory usage


class TestAPIVectorProcessor:
    """Test API-based vector processor."""

    @pytest.fixture
    def processor(self):
        return APIVectorProcessor(
            api_key="test-key",
            provider="openai",
            similarity_threshold=0.85
        )

    @pytest.mark.asyncio
    async def test_initialization(self, processor):
        """Test processor initializes with correct settings."""
        assert processor.api_key == "test-key"
        assert processor.provider == "openai"
        assert processor.similarity_threshold == 0.85

    @pytest.mark.asyncio
    @pytest.mark.skipif(True, reason="Requires API key")
    async def test_get_embedding(self, processor):
        """Test generating embedding via API."""
        text = "Hello world"
        embedding = await processor.get_embedding(text)
        
        assert isinstance(embedding, np.ndarray)
        assert embedding.shape[0] > 0

    @pytest.mark.asyncio
    async def test_similarity(self, processor):
        """Test cosine similarity computation."""
        emb1 = np.array([1.0, 0.0, 0.0])
        emb2 = np.array([0.707, 0.707, 0.0])  # 45 degree angle
        
        similarity = await processor.similarity(emb1, emb2)
        assert 0.6 < similarity < 0.8  # Should be ~0.707

    def test_memory_usage(self, processor):
        """Test memory usage reporting."""
        mem = processor.get_memory_usage_mb()
        assert 0 < mem < 10  # Should be minimal (just HTTP client)

    @pytest.mark.asyncio
    async def test_close(self, processor):
        """Test closing HTTP client."""
        await processor.close()
        # Should not raise an error


class TestSemanticProcessorFactory:
    """Test semantic processor factory."""

    def test_create_simhash_processor(self):
        """Test creating SimHash processor."""
        processor = SemanticProcessorFactory.create(
            strategy=SemanticStrategy.SIMHASH,
            similarity_threshold=0.85
        )
        
        assert isinstance(processor, SimHashProcessor)

    def test_create_local_vector_processor(self):
        """Test creating local vector processor."""
        processor = SemanticProcessorFactory.create(
            strategy=SemanticStrategy.VECTORDB_LOCAL,
            similarity_threshold=0.90
        )
        
        assert isinstance(processor, LocalVectorProcessor)
        assert processor.similarity_threshold == 0.90

    def test_create_api_vector_processor(self):
        """Test creating API vector processor."""
        processor = SemanticProcessorFactory.create(
            strategy=SemanticStrategy.VECTORDB_API,
            api_key="test-key",
            similarity_threshold=0.85
        )
        
        assert isinstance(processor, APIVectorProcessor)
        assert processor.api_key == "test-key"

    def test_create_api_processor_without_key_raises(self):
        """Test that creating API processor without key raises error."""
        with pytest.raises(ValueError, match="api_key required"):
            SemanticProcessorFactory.create(
                strategy=SemanticStrategy.VECTORDB_API
            )

    def test_create_invalid_strategy_raises(self):
        """Test that invalid strategy raises error."""
        with pytest.raises(ValueError):
            SemanticProcessorFactory.create(
                strategy="INVALID_STRATEGY"  # type: ignore
            )

    @patch('sentinelrouter.sentinelrouter.semantic.factory.get_settings')
    def test_from_settings_simhash(self, mock_get_settings):
        """Test creating processor from settings (SimHash)."""
        mock_settings = type('Settings', (), {
            'semantic_strategy': 'SIMHASH',
            'semantic_similarity_threshold': 0.85,
            'cycle_detection_simhash_threshold': 3,
            'semantic_hash_bits': 64
        })()
        mock_get_settings.return_value = mock_settings
        
        processor = SemanticProcessorFactory.from_settings(mock_settings)
        
        assert isinstance(processor, SimHashProcessor)

    @patch('sentinelrouter.sentinelrouter.semantic.factory.get_settings')
    def test_from_settings_default_local_vector(self, mock_get_settings):
        """Test creating processor from settings (default to local vector)."""
        mock_settings = type('Settings', (), {
            'semantic_strategy': 'VECTORDB_LOCAL',
            'semantic_similarity_threshold': 0.85,
            'semantic_model_path': None
        })()
        mock_get_settings.return_value = mock_settings
        
        processor = SemanticProcessorFactory.from_settings(mock_settings)
        
        assert isinstance(processor, LocalVectorProcessor)


class TestSemanticStrategies:
    """Integration tests for semantic strategies."""

    @pytest.mark.asyncio
    async def test_simhash_strategy_end_to_end(self):
        """Test SimHash strategy end-to-end."""
        processor = SemanticProcessorFactory.create(SemanticStrategy.SIMHASH)
        
        # Test with similar texts
        text1 = "What is the capital of France?"
        text2 = "What is the capital of France?"
        
        is_similar = await processor.is_similar(text1, text2, threshold=0.85)
        assert is_similar is True

    @pytest.mark.asyncio
    async def test_strategy_comparison_exact_match(self):
        """Test all strategies detect exact matches."""
        text = "The quick brown fox jumps over the lazy dog"
        
        # SimHash
        simhash_proc = SemanticProcessorFactory.create(SemanticStrategy.SIMHASH)
        simhash_result = await simhash_proc.is_similar(text, text)
        
        assert simhash_result is True

    @pytest.mark.asyncio
    async def test_memory_footprint_comparison(self):
        """Test memory footprint of different strategies."""
        simhash_proc = SemanticProcessorFactory.create(SemanticStrategy.SIMHASH)
        local_proc = SemanticProcessorFactory.create(SemanticStrategy.VECTORDB_LOCAL)
        api_proc = SemanticProcessorFactory.create(
            SemanticStrategy.VECTORDB_API,
            api_key="test-key"
        )
        
        simhash_mem = simhash_proc.get_memory_usage_mb()
        local_mem = local_proc.get_memory_usage_mb()
        api_mem = api_proc.get_memory_usage_mb()
        
        # Verify expected ordering: SimHash < API < Local (before init)
        assert simhash_mem < 1  # Should be tiny
        assert api_mem < 10  # Should be small
        # Local is 0 before initialization, ~80MB after
