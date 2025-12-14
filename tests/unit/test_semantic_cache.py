import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure required settings are present before importing settings-dependent modules
os.environ["DEEPSEEK_API_KEY"] = "mock-deepseek-key"
os.environ["ANTHROPIC_API_KEY"] = "mock-anthropic-key"

from sentinelrouter.sentinelrouter.models import Base  # noqa: E402
from sentinelrouter.sentinelrouter.semantic_cache import SemanticCache  # noqa: E402
from sentinelrouter.sentinelrouter.config import get_settings

settings = get_settings()


def _make_cache(min_samples: int = 3):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    cache = SemanticCache(
        session,
        min_samples=min_samples,
        confidence_threshold=settings.semantic_cache_confidence_threshold,
        ttl_seconds=settings.semantic_cache_ttl_seconds,
    )
    return cache


def test_semantic_hash_changes_with_context():
    cache = _make_cache()
    prompt = "Summarize the latest news"
    context_a = [{"role": "user", "content": "A"}]
    context_b = [{"role": "user", "content": "B"}]

    hash_a = cache.build_semantic_hash(prompt, context_a)
    hash_b = cache.build_semantic_hash(prompt, context_b)

    assert hash_a != hash_b


def test_confidence_requires_min_samples():
    prompt = "Explain quantum tunneling"
    context = [{"role": "user", "content": prompt}]
    cache = _make_cache(min_samples=3)

    confident, confidence = cache.has_confident_history(prompt, context)
    assert not confident
    assert confidence == 0.0

    for _ in range(2):
        cache.record_interaction(
            prompt=prompt,
            context=context,
            response_text="ok",
            model_used=settings.weak_model_id,
            latency_ms=25.0,
            judge_invoked=True,
            judge_latency_ms=5.0,
            complexity_score=0.2,
            impact_scope="LOW",
            cost=0.01,
            total_tokens=12,
        )

    confident, confidence = cache.has_confident_history(prompt, context)
    # Still below minimum sample size
    assert not confident
    assert confidence == 0.0

    cache.record_interaction(
        prompt=prompt,
        context=context,
        response_text="ok",
        model_used=settings.weak_model_id,
        latency_ms=30.0,
        judge_invoked=True,
        judge_latency_ms=4.0,
        complexity_score=0.25,
        impact_scope="LOW",
        cost=0.02,
        total_tokens=15,
    )

    confident, confidence = cache.has_confident_history(prompt, context)
    assert confident
    assert confidence >= settings.semantic_cache_confidence_threshold


def test_stats_capture_latency_and_metadata():
    prompt = "Translate to French"
    context = [{"role": "user", "content": prompt}]
    cache = _make_cache(min_samples=1)

    stats = cache.record_interaction(
        prompt=prompt,
        context=context,
        response_text="Bonjour",
        model_used=settings.strong_model_id,
        latency_ms=120.0,
        judge_invoked=True,
        judge_latency_ms=12.0,
        complexity_score=0.8,
        impact_scope="HIGH",
        cost=0.05,
        total_tokens=42,
    )

    summary = cache.summarize_stats(stats.semantic_hash)
    assert summary is not None
    assert summary["total_calls"] == 1
    assert summary["total_tokens"] == 42
    assert summary["mean_latency_ms"] == pytest.approx(120.0)
    assert summary["confidence"] > 0.0
