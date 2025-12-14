"""
Test cache-based routing decisions in semantic cache.

Verifies that:
1. Cache skips judge when confidence is high
2. Cache routes to weak model when history shows weak usage
3. Cache routes to strong model when history shows strong usage
"""

import pytest
from sentinelrouter.sentinelrouter.semantic_cache import SemanticCache
from sentinelrouter.sentinelrouter.database import get_db, init_db
from sentinelrouter.sentinelrouter.config import get_settings


@pytest.fixture
def cache():
    """Create a semantic cache instance with fresh test database."""
    import tempfile
    import os
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sentinelrouter.sentinelrouter.models import Base
    
    # Create temporary database
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    
    engine = create_engine(f'sqlite:///{db_path}')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        yield SemanticCache(
            session, 
            min_samples=3,
            confidence_threshold=0.75,
        )
    finally:
        session.close()
        engine.dispose()
        os.unlink(db_path)


def test_cache_recommends_weak_after_weak_history(cache):
    """Test that cache recommends weak model after consistent weak usage."""
    settings = get_settings()
    prompt = "What is 2+2?"
    context = [{"role": "user", "content": "What is 2+2?"}]
    
    # Record 5 weak model interactions
    for i in range(5):
        cache.record_interaction(
            prompt=prompt,
            context=context,
            response_text=f"Response {i}",
            model_used=settings.weak_model_id,  # Weak model
            latency_ms=100.0,
            judge_invoked=True,
            judge_latency_ms=50.0,
            complexity_score=0.2,
            impact_scope="LOW",
            cost=0.001,
            total_tokens=10,
        )
    
    # Check recommendation
    recommendation = cache.get_recommended_route(prompt, context)
    assert recommendation == "weak", "Cache should recommend weak model after 5 weak calls"
    
    # Verify confidence
    confident, confidence = cache.has_confident_history(prompt, context)
    assert confident is True, "Should be confident after 5 consistent calls"
    assert confidence >= 0.75, f"Confidence should be >= 0.75, got {confidence}"


def test_cache_recommends_strong_after_strong_history(cache):
    """Test that cache recommends strong model after consistent strong usage."""
    settings = get_settings()
    prompt = "Explain quantum mechanics in detail"
    context = [{"role": "user", "content": "Explain quantum mechanics in detail"}]
    
    # Record 4 strong model interactions
    for i in range(4):
        cache.record_interaction(
            prompt=prompt,
            context=context,
            response_text=f"Complex response {i}",
            model_used=settings.strong_model_id,  # Strong model
            latency_ms=500.0,
            judge_invoked=True,
            judge_latency_ms=50.0,
            complexity_score=0.9,
            impact_scope="HIGH",
            cost=0.05,
            total_tokens=1000,
        )
    
    # Check recommendation
    recommendation = cache.get_recommended_route(prompt, context)
    assert recommendation == "strong", "Cache should recommend strong model after 4 strong calls"
    
    # Verify confidence
    confident, confidence = cache.has_confident_history(prompt, context)
    assert confident is True, "Should be confident after 4 consistent calls"


def test_cache_no_recommendation_with_mixed_history(cache):
    """Test that cache doesn't recommend when history is mixed (low confidence)."""
    settings = get_settings()
    prompt = "Medium complexity query"
    context = [{"role": "user", "content": "Medium complexity query"}]
    
    # Record mixed interactions (2 weak, 2 strong)
    for i in range(2):
        cache.record_interaction(
            prompt=prompt,
            context=context,
            response_text=f"Response {i}",
            model_used=settings.weak_model_id,
            latency_ms=100.0,
            judge_invoked=True,
            judge_latency_ms=50.0,
            complexity_score=0.4,
            impact_scope="MEDIUM",
            cost=0.001,
            total_tokens=10,
        )
    
    for i in range(2):
        cache.record_interaction(
            prompt=prompt,
            context=context,
            response_text=f"Response {i}",
            model_used=settings.strong_model_id,
            latency_ms=500.0,
            judge_invoked=True,
            judge_latency_ms=50.0,
            complexity_score=0.8,
            impact_scope="HIGH",
            cost=0.05,
            total_tokens=1000,
        )
    
    # Check recommendation - should be None or at least not confident
    confident, confidence = cache.has_confident_history(prompt, context)
    assert confident is False, "Should not be confident with 50/50 split"
    assert confidence < 0.75, f"Confidence should be < 0.75 with mixed history, got {confidence}"


def test_cache_no_recommendation_insufficient_samples(cache):
    """Test that cache requires minimum samples before being confident."""
    settings = get_settings()
    prompt = "New query"
    context = [{"role": "user", "content": "New query"}]
    
    # Record only 2 interactions (below min_samples=3)
    for i in range(2):
        cache.record_interaction(
            prompt=prompt,
            context=context,
            response_text=f"Response {i}",
            model_used=settings.weak_model_id,
            latency_ms=100.0,
            judge_invoked=True,
            judge_latency_ms=50.0,
            complexity_score=0.2,
            impact_scope="LOW",
            cost=0.001,
            total_tokens=10,
        )
    
    # Should not be confident yet
    confident, confidence = cache.has_confident_history(prompt, context)
    assert confident is False, "Should not be confident with only 2 samples (min is 3)"


def test_cache_stats_tracking(cache):
    """Test that cache properly tracks statistics."""
    settings = get_settings()
    prompt = "Test query"
    context = [{"role": "user", "content": "Test query"}]
    
    # Record 3 weak, 1 strong
    for i in range(3):
        cache.record_interaction(
            prompt=prompt,
            context=context,
            response_text=f"Response {i}",
            model_used=settings.weak_model_id,
            latency_ms=100.0,
            judge_invoked=True,
            judge_latency_ms=50.0,
            complexity_score=0.2,
            impact_scope="LOW",
            cost=0.001,
            total_tokens=10,
        )
    
    cache.record_interaction(
        prompt=prompt,
        context=context,
        response_text="Strong response",
        model_used=settings.strong_model_id,
        latency_ms=500.0,
        judge_invoked=True,
        judge_latency_ms=50.0,
        complexity_score=0.9,
        impact_scope="HIGH",
        cost=0.05,
        total_tokens=1000,
    )
    
    # Get stats
    stats = cache.get_stats_for_prompt(prompt, context)
    assert stats is not None
    assert stats.total_calls == 4
    assert stats.weak_calls == 3
    assert stats.strong_calls == 1
    assert stats.judge_invocations == 4
    
    # Confidence should be 3/4 = 0.75 (dominant is weak with 3 calls)
    confidence = cache.confidence_for_hash(stats.semantic_hash)
    assert confidence == 0.75, f"Expected confidence 0.75, got {confidence}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
