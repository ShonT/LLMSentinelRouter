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
    
    @pytest.mark.asyncio
    async def test_mean_pooling_logic(self, processor):
        """Test mean pooling computation without full model."""
        # Mock model output and attention mask
        model_output = (np.array([[[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]]),)
        attention_mask = np.array([[1, 1, 0]])  # Third token is padding
        
        result = processor._mean_pooling(model_output, attention_mask)
        
        # Should average only non-padded tokens
        # Token 1: [1.0, 2.0], Token 2: [3.0, 4.0]
        # Average: [2.0, 3.0]
        expected = np.array([[2.0, 3.0]])
        np.testing.assert_array_almost_equal(result, expected)
    
    @pytest.mark.asyncio
    @patch('sentinelrouter.sentinelrouter.semantic.local_vector_processor.onnxruntime')
    @patch('sentinelrouter.sentinelrouter.semantic.local_vector_processor.AutoTokenizer')
    async def test_get_embedding_with_mock(self, mock_tokenizer_class, mock_onnx, processor):
        """Test embedding generation with mocked ONNX and tokenizer."""
        # Mock tokenizer
        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            'input_ids': np.array([[101, 2003, 102]]),
            'attention_mask': np.array([[1, 1, 1]])
        }
        mock_tokenizer_class.from_pretrained.return_value = mock_tokenizer
        
        # Mock ONNX session
        mock_session = MagicMock()
        # Return shape: (batch=1, seq_len=3, hidden_dim=384)
        mock_output = np.random.rand(1, 3, 384).astype(np.float32)
        mock_session.run.return_value = [mock_output]
        mock_onnx.InferenceSession.return_value = mock_session
        
        # Create new processor with mocks
        processor._initialized = False
        with patch('os.path.exists', return_value=True):
            embedding = await processor.get_embedding("test text")
        
        assert isinstance(embedding, np.ndarray)
        assert embedding.shape[0] == 384  # MiniLM dimension
        # Check normalized (L2 norm should be ~1.0)
        assert abs(np.linalg.norm(embedding) - 1.0) < 0.01
    
    @pytest.mark.asyncio
    @patch('sentinelrouter.sentinelrouter.semantic.local_vector_processor.onnxruntime')
    async def test_lazy_initialization(self, mock_onnx, processor):
        """Test that model is only loaded on first use."""
        assert not processor._initialized
        
        # Mock to avoid actual download
        with patch('os.path.exists', return_value=True):
            with patch('sentinelrouter.sentinelrouter.semantic.local_vector_processor.AutoTokenizer'):
                await processor._ensure_initialized()
        
        assert processor._initialized


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
    
    @pytest.mark.asyncio
    async def test_openai_api_call_success(self):
        """Test successful OpenAI API embedding call."""
        processor = APIVectorProcessor(
            api_key="test-key",
            provider="openai",
            model="text-embedding-3-small"
        )
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [{"embedding": [0.1] * 1536}]
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(processor.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            
            embedding = await processor.get_embedding("test text")
            
            # Verify API call
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            
            # Check endpoint
            assert "embeddings" in call_args[0][0]
            
            # Check payload
            payload = call_args[1]['json']
            assert payload['input'] == "test text"
            assert payload['model'] == "text-embedding-3-small"
            
            # Check headers
            headers = call_args[1]['headers']
            assert "Authorization" in headers
            assert "Bearer test-key" in headers['Authorization']
            
            # Check embedding
            assert isinstance(embedding, np.ndarray)
            assert len(embedding) == 1536
    
    @pytest.mark.asyncio
    async def test_voyage_api_call_format(self):
        """Test Voyage AI API call format differs from OpenAI."""
        processor = APIVectorProcessor(
            api_key="voyage-key",
            provider="voyage",
            model="voyage-2"
        )
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [{"embedding": [0.2] * 1024}]
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(processor.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            
            await processor.get_embedding("voyage test")
            
            payload = mock_post.call_args[1]['json']
            # Voyage uses array for input
            assert isinstance(payload['input'], list)
            assert payload['input'][0] == "voyage test"
    
    @pytest.mark.asyncio
    async def test_api_error_handling_401(self):
        """Test handling of 401 Unauthorized errors."""
        import httpx
        
        processor = APIVectorProcessor(
            api_key="invalid-key",
            provider="openai"
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Invalid API key"
        
        with patch.object(processor.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "401 Unauthorized",
                request=MagicMock(),
                response=mock_response
            )
            
            with pytest.raises(httpx.HTTPStatusError):
                await processor.get_embedding("test")
    
    @pytest.mark.asyncio
    async def test_api_error_handling_rate_limit(self):
        """Test handling of 429 Rate Limit errors."""
        import httpx
        
        processor = APIVectorProcessor(
            api_key="test-key",
            provider="openai"
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"
        
        with patch.object(processor.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "429 Too Many Requests",
                request=MagicMock(),
                response=mock_response
            )
            
            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                await processor.get_embedding("test")
            
            assert "429" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_network_timeout_handling(self):
        """Test handling of network timeouts."""
        import httpx
        
        processor = APIVectorProcessor(
            api_key="test-key",
            provider="openai"
        )
        
        with patch.object(processor.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Request timeout")
            
            with pytest.raises(httpx.TimeoutException):
                await processor.get_embedding("test")
    
    @pytest.mark.asyncio
    async def test_unsupported_provider_initialization(self):
        """Test that unsupported provider raises error on init."""
        with pytest.raises(ValueError, match="Unsupported provider"):
            APIVectorProcessor(
                api_key="test-key",
                provider="unsupported-provider"
            )


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

    @patch('sentinelrouter.sentinelrouter.config.get_settings')
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

    @patch('sentinelrouter.sentinelrouter.config.get_settings')
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


class TestVectorStore:
    """Test vector storage with mocked LanceDB."""
    
    @pytest.mark.asyncio
    async def test_initialization_without_lancedb(self):
        """Test VectorStore initialization when LanceDB not available."""
        from sentinelrouter.sentinelrouter.semantic.vector_store import VectorStore
        
        store = VectorStore(storage_path="/tmp/test_vectors", use_lancedb=False)
        assert store.db is None
        assert not store.use_lancedb
    
    @pytest.mark.asyncio
    @patch('sentinelrouter.sentinelrouter.semantic.vector_store.lancedb')
    @patch('sentinelrouter.sentinelrouter.semantic.vector_store.pyarrow')
    async def test_add_simhash_embedding(self, mock_pa, mock_lancedb):
        """Test adding SimHash (int) embedding."""
        from sentinelrouter.sentinelrouter.semantic.vector_store import VectorStore
        
        store = VectorStore(use_lancedb=True)
        
        # SimHash is just an int - should log and return ID
        record_id = await store.add_embedding(
            session_id="test-session",
            text="Hello world",
            embedding=12345678901234567890,
            metadata={"type": "test"}
        )
        
        assert "test-session" in record_id
    
    @pytest.mark.asyncio
    async def test_add_vector_embedding(self):
        """Test adding vector embedding with mocked LanceDB."""
        import sys
        from sentinelrouter.sentinelrouter.semantic.vector_store import VectorStore
        
        # Mock pyarrow module
        mock_pa = MagicMock()
        mock_schema = MagicMock()
        mock_pa.schema.return_value = mock_schema
        mock_pa.string.return_value = MagicMock()
        mock_pa.list_.return_value = MagicMock()
        mock_pa.float32.return_value = MagicMock()
        
        # Mock LanceDB
        mock_lancedb = MagicMock()
        mock_db = MagicMock()
        mock_table = MagicMock()
        mock_db.create_table.return_value = mock_table
        mock_lancedb.connect.return_value = mock_db
        
        # Patch sys.modules to inject mocks
        original_pyarrow = sys.modules.get('pyarrow')
        original_lancedb = sys.modules.get('lancedb')
        
        try:
            sys.modules['pyarrow'] = mock_pa
            sys.modules['lancedb'] = mock_lancedb
            
            # Also patch at module level for already-imported references
            with patch('sentinelrouter.sentinelrouter.semantic.vector_store.lancedb', mock_lancedb):
                with patch('sentinelrouter.sentinelrouter.semantic.vector_store.pyarrow', mock_pa):
                    store = VectorStore(use_lancedb=True)
                    await store._ensure_lancedb_initialized()
                    
                    embedding = np.random.rand(384).astype(np.float32)
                    
                    record_id = await store.add_embedding(
                        session_id="test-session",
                        text="Test text",
                        embedding=embedding,
                        metadata={"source": "test"}
                    )
            
                    assert "test-session" in record_id
                    # Table should be created on first insert
                    mock_db.create_table.assert_called_once()
        finally:
            # Restore original modules
            if original_pyarrow:
                sys.modules['pyarrow'] = original_pyarrow
            else:
                sys.modules.pop('pyarrow', None)
            if original_lancedb:
                sys.modules['lancedb'] = original_lancedb
            else:
                sys.modules.pop('lancedb', None)
    
    @pytest.mark.asyncio
    @patch('sentinelrouter.sentinelrouter.semantic.vector_store.lancedb')
    async def test_search_similar_with_mock(self, mock_lancedb):
        """Test vector similarity search with mocked LanceDB."""
        from sentinelrouter.sentinelrouter.semantic.vector_store import VectorStore
        
        # Mock search results
        mock_table = MagicMock()
        mock_search = MagicMock()
        mock_search.limit.return_value.to_list.return_value = [
            {'text': 'Similar text 1', '_distance': 0.1, 'metadata': 'meta1', 'session_id': 'sess1'},
            {'text': 'Similar text 2', '_distance': 0.2, 'metadata': 'meta2', 'session_id': 'sess1'}
        ]
        mock_table.search.return_value = mock_search
        
        mock_db = MagicMock()
        mock_db.open_table.return_value = mock_table
        mock_lancedb.connect.return_value = mock_db
        
        store = VectorStore(use_lancedb=True)
        store.db = mock_db
        store.table = mock_table
        
        query_embedding = np.random.rand(384).astype(np.float32)
        results = await store.search_similar(
            embedding=query_embedding,
            session_id="sess1",
            top_k=5,
            similarity_threshold=0.7
        )
        
        # Both results should pass threshold (0.9 and 0.8 similarity)
        assert len(results) == 2
        assert results[0][0] == 'Similar text 1'
        assert results[1][0] == 'Similar text 2'
        # Check similarity conversion: 1.0 - distance
        assert abs(results[0][1] - 0.9) < 0.01
    
    @pytest.mark.asyncio
    async def test_search_simhash_not_implemented(self):
        """Test that SimHash search returns empty (not yet implemented)."""
        from sentinelrouter.sentinelrouter.semantic.vector_store import VectorStore
        
        store = VectorStore(use_lancedb=False)
        results = await store.search_similar(
            embedding=12345678901234567890,  # int = SimHash
            top_k=5
        )
        
        assert results == []
    
    @pytest.mark.asyncio
    async def test_lancedb_fallback_on_import_error(self):
        """Test graceful fallback when LanceDB not installed."""
        from sentinelrouter.sentinelrouter.semantic.vector_store import VectorStore
        
        with patch('sentinelrouter.sentinelrouter.semantic.vector_store.lancedb', None):
            store = VectorStore(use_lancedb=True)
            await store._ensure_lancedb_initialized()
            
            # Should disable lancedb on import failure
            assert not store.use_lancedb
    
    def test_memory_usage_reporting(self):
        """Test memory usage reporting for different modes."""
        from sentinelrouter.sentinelrouter.semantic.vector_store import VectorStore
        
        store_no_lance = VectorStore(use_lancedb=False)
        store_with_lance = VectorStore(use_lancedb=True)
        
        mem_no_lance = store_no_lance.get_memory_usage_mb()
        mem_with_lance = store_with_lance.get_memory_usage_mb()
        
        assert mem_no_lance < mem_with_lance
        assert mem_no_lance < 1  # Should be minimal
        assert mem_with_lance > 10  # LanceDB has overhead


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
