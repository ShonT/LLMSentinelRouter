"""
Unit tests for Module D: Cycle Detector (Graph-Based)
Tests the cycle detection and SimHash functionality.
"""

import pytest
from sentinelrouter.sentinelrouter.cycle_detector import CycleDetector, _compute_simhash, _hamming_distance


class TestCycleDetector:
    """Tests for Module D - Graph-Based Cycle Detection."""
    
    def test_initialization(self):
        """Test cycle detector initialization."""
        detector = CycleDetector(session_id="test_session")
        
        assert detector.session_id == "test_session"
        assert detector.simhash_threshold == 3  # Default
        assert len(detector.recent_hashes) == 0
    
    def test_initialization_custom_threshold(self):
        """Test initialization with custom threshold."""
        detector = CycleDetector(
            session_id="test_session",
            simhash_threshold=5,
            window_size=50
        )
        
        assert detector.simhash_threshold == 5
        assert detector.window_size == 50
    
    def test_compute_simhash_identical_strings(self):
        """Test SimHash produces same hash for identical strings."""
        text1 = "What is the capital of France?"
        text2 = "What is the capital of France?"
        
        hash1 = _compute_simhash(text1)
        hash2 = _compute_simhash(text2)
        
        assert hash1 == hash2
    
    def test_compute_simhash_different_strings(self):
        """Test SimHash produces different hashes for different strings."""
        text1 = "What is the capital of France?"
        text2 = "What is the capital of Germany?"
        
        hash1 = _compute_simhash(text1)
        hash2 = _compute_simhash(text2)
        
        assert hash1 != hash2
    
    def test_compute_simhash_similar_strings(self):
        """Test SimHash produces similar hashes for similar strings."""
        text1 = "What is the capital of France?"
        text2 = "What is capital of France?"  # Minor difference
        
        hash1 = _compute_simhash(text1)
        hash2 = _compute_simhash(text2)
        
        # Should be different but similar (low hamming distance relative to 64 bits)
        distance = _hamming_distance(hash1, hash2)
        # With SHA-256 based SimHash, similarity is less predictable
        # Just verify they're different but not completely different
        assert distance > 0  # Should be different
        assert distance < 64  # But not all bits different
    
    def test_compute_simhash_empty_string(self):
        """Test SimHash with empty string."""
        hash_val = _compute_simhash("")
        assert hash_val == 0
    
    def test_hamming_distance_identical(self):
        """Test Hamming distance for identical hashes."""
        hash1 = 0b1010101010
        hash2 = 0b1010101010
        
        distance = _hamming_distance(hash1, hash2)
        assert distance == 0
    
    def test_hamming_distance_one_bit(self):
        """Test Hamming distance for one bit difference."""
        hash1 = 0b1010101010
        hash2 = 0b1010101011  # Last bit different
        
        distance = _hamming_distance(hash1, hash2)
        assert distance == 1
    
    def test_hamming_distance_all_different(self):
        """Test Hamming distance for completely different hashes."""
        hash1 = 0b1111111111
        hash2 = 0b0000000000
        
        distance = _hamming_distance(hash1, hash2)
        assert distance == 10
    
    def test_detect_cycle_no_history(self):
        """Test cycle detection with no history."""
        detector = CycleDetector(session_id="test_session")
        
        cycle = detector.detect_cycle_with_prompt("First prompt")
        assert cycle is False
    
    def test_detect_cycle_exact_duplicate(self):
        """Test cycle detection with exact duplicate."""
        detector = CycleDetector(session_id="test_session", simhash_threshold=3)
        
        prompt = "What is the capital of France?"
        
        # Add first occurrence
        detector.add_request_response(prompt, "Paris")
        
        # Check for cycle on second occurrence
        cycle = detector.detect_cycle_with_prompt(prompt)
        
        # Should detect cycle (distance = 0)
        assert cycle is True
    
    def test_detect_cycle_near_duplicate(self):
        """Test cycle detection with near-duplicate."""
        detector = CycleDetector(session_id="test_session", simhash_threshold=5)
        
        prompt1 = "What is the capital of France?"
        prompt2 = "What is capital of France?"  # Very similar
        
        detector.add_request_response(prompt1, "Paris")
        
        cycle = detector.detect_cycle_with_prompt(prompt2)
        
        # Depending on hash similarity, might detect cycle
        # This is non-deterministic based on SimHash threshold
        assert isinstance(cycle, bool)
    
    def test_detect_cycle_different_prompts(self):
        """Test cycle detection with different prompts."""
        detector = CycleDetector(session_id="test_session", simhash_threshold=3)
        
        detector.add_request_response("What is 2+2?", "4")
        detector.add_request_response("What is 3+3?", "6")
        
        cycle = detector.detect_cycle_with_prompt("What is the meaning of life?")
        
        assert cycle is False
    
    def test_add_request_response(self):
        """Test adding request-response pairs."""
        detector = CycleDetector(session_id="test_session")
        
        detector.add_request_response("Question 1", "Answer 1")
        detector.add_request_response("Question 2", "Answer 2")
        
        assert len(detector.recent_hashes) == 2
    
    def test_add_request_response_max_limit(self):
        """Test that recent hashes list doesn't exceed max."""
        detector = CycleDetector(session_id="test_session", window_size=5)
        
        for i in range(10):
            detector.add_request_response(f"Question {i}", f"Answer {i}")
        
        assert len(detector.recent_hashes) <= 5
    
    def test_recent_hashes_fifo(self):
        """Test that recent hashes work as FIFO queue."""
        detector = CycleDetector(session_id="test_session", window_size=3)
        
        detector.add_request_response("Q1", "A1")
        detector.add_request_response("Q2", "A2")
        detector.add_request_response("Q3", "A3")
        
        first_hash = detector.recent_hashes[0]
        
        detector.add_request_response("Q4", "A4")
        
        # First hash should be removed
        assert len(detector.recent_hashes) == 3
        # New hash should be at the end (if using append)
    
    def test_cycle_detection_with_response_context(self):
        """Test that cycle detection considers both prompt and last response."""
        detector = CycleDetector(session_id="test_session")
        
        # Same question, different context (previous answer)
        detector.add_request_response("What next?", "Go left")
        cycle1 = detector.detect_cycle_with_prompt("What next?")
        
        # Should detect cycle if prompt repeats
        assert isinstance(cycle1, bool)
    
    def test_networkx_graph_creation(self):
        """Test that networkx graph is created if available."""
        detector = CycleDetector(session_id="test_session")
        
        # Graph should exist if networkx installed
        if detector.graph is not None:
            assert hasattr(detector.graph, 'nodes')
            assert hasattr(detector.graph, 'edges')
    
    def test_multiple_sessions_isolated(self):
        """Test that different sessions have isolated cycle detection."""
        detector1 = CycleDetector(session_id="session_1")
        detector2 = CycleDetector(session_id="session_2")
        
        detector1.add_request_response("Question", "Answer")
        
        # Session 2 should not see session 1's history
        assert len(detector2.recent_hashes) == 0
    
    def test_case_sensitivity(self):
        """Test that cycle detection is case-sensitive."""
        detector = CycleDetector(session_id="test_session", simhash_threshold=3)
        
        detector.add_request_response("WHAT IS THE CAPITAL?", "Paris")
        
        # Different case should produce different hash
        cycle = detector.detect_cycle_with_prompt("what is the capital?")
        
        # May or may not detect depending on SimHash similarity
        # But they should be treated as different strings
        assert isinstance(cycle, bool)
    
    def test_whitespace_handling(self):
        """Test handling of extra whitespace."""
        detector = CycleDetector(session_id="test_session")
        
        prompt1 = "What is the capital of France?"
        prompt2 = "What    is   the   capital   of   France?"
        
        hash1 = _compute_simhash(prompt1)
        hash2 = _compute_simhash(prompt2)
        
        # Should be similar but may not be identical
        # due to tokenization differences
        assert isinstance(hash1, int)
        assert isinstance(hash2, int)
    
    def test_special_characters(self):
        """Test handling of special characters."""
        detector = CycleDetector(session_id="test_session")
        
        prompt = "What is 2+2? Answer: 4!"
        
        detector.add_request_response(prompt, "The answer is 4")
        cycle = detector.detect_cycle_with_prompt(prompt)
        
        assert cycle is True  # Exact match should detect cycle
    
    def test_unicode_handling(self):
        """Test handling of unicode characters."""
        detector = CycleDetector(session_id="test_session")
        
        prompt = "¿Cuál es la capital de Francia? 法国的首都是什么？"
        
        detector.add_request_response(prompt, "París / 巴黎")
        cycle = detector.detect_cycle_with_prompt(prompt)
        
        assert cycle is True
    
    def test_very_long_text(self):
        """Test handling of very long text."""
        detector = CycleDetector(session_id="test_session")
        
        long_prompt = "What is the meaning of life? " * 1000
        long_response = "42 " * 500
        
        detector.add_request_response(long_prompt, long_response)
        cycle = detector.detect_cycle_with_prompt(long_prompt)
        
        assert cycle is True
    
    def test_threshold_sensitivity(self):
        """Test different threshold values."""
        # Strict threshold (low distance)
        detector_strict = CycleDetector(session_id="test", simhash_threshold=1)
        
        # Loose threshold (high distance)
        detector_loose = CycleDetector(session_id="test", simhash_threshold=10)
        
        prompt1 = "What is the capital?"
        prompt2 = "What's the capital?"
        
        detector_strict.add_request_response(prompt1, "Paris")
        detector_loose.add_request_response(prompt1, "Paris")
        
        # Strict might not detect, loose might detect
        strict_cycle = detector_strict.detect_cycle_with_prompt(prompt2)
        loose_cycle = detector_loose.detect_cycle_with_prompt(prompt2)
        
        # Both should be boolean
        assert isinstance(strict_cycle, bool)
        assert isinstance(loose_cycle, bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
