"""
Unit tests for the sliding window rate limiter.
"""

import asyncio
import pytest
from datetime import datetime, timedelta, timezone

from sentinelrouter.sentinelrouter.rate_limiter import RateLimiter, RateLimitWindow


class TestRateLimitWindow:
    """Test individual rate limit window functionality."""
    
    @pytest.mark.asyncio
    async def test_add_request(self):
        """Test adding requests to the window."""
        window = RateLimitWindow(model_id="test-model")
        
        await window.add_request(tokens=100)
        await window.add_request(tokens=200)
        
        usage = await window.get_current_usage()
        assert usage['requests_last_minute'] == 2
        assert usage['tokens_last_minute'] == 300
        assert usage['requests_last_day'] == 2
        assert usage['tokens_last_day'] == 300
    
    @pytest.mark.asyncio
    async def test_cleanup_expired_entries(self):
        """Test that old entries are removed."""
        window = RateLimitWindow(model_id="test-model")
        
        # Add old entry (should be cleaned up)
        old_time = datetime.now(timezone.utc) - timedelta(minutes=2)
        window.requests_minute.append((old_time, 100))
        
        # Add recent entry
        await window.add_request(tokens=200)
        
        usage = await window.get_current_usage()
        # Old entry should be cleaned up
        assert usage['requests_last_minute'] == 1
        assert usage['tokens_last_minute'] == 200
    
    @pytest.mark.asyncio
    async def test_check_limits_rpm(self):
        """Test RPM limit checking."""
        window = RateLimitWindow(model_id="test-model")
        
        # Add requests up to limit
        for i in range(10):
            await window.add_request(tokens=10)
        
        # Should allow up to 95% of 10 (safety margin)
        allowed, reason = await window.check_limits(rpm_limit=10, safety_margin=0.95)
        assert not allowed
        assert "RPM limit" in reason
        
        # Should allow if limit is higher
        allowed, reason = await window.check_limits(rpm_limit=20, safety_margin=0.95)
        assert allowed
        assert reason is None
    
    @pytest.mark.asyncio
    async def test_check_limits_tpm(self):
        """Test TPM limit checking."""
        window = RateLimitWindow(model_id="test-model")
        
        # Add tokens up to limit
        await window.add_request(tokens=1000)
        
        # Should block at 95% of 1000
        allowed, reason = await window.check_limits(tpm_limit=1000, safety_margin=0.95)
        assert not allowed
        assert "TPM limit" in reason
    
    @pytest.mark.asyncio
    async def test_daily_reset(self):
        """Test daily counter reset."""
        window = RateLimitWindow(model_id="test-model")
        
        # Add some requests
        await window.add_request(tokens=100)
        
        # Simulate day passing
        window.last_daily_reset = datetime.now(timezone.utc) - timedelta(days=1, hours=1)
        
        await window.reset_daily_counters()
        
        usage = await window.get_current_usage()
        assert usage['requests_last_day'] == 0
        assert usage['tokens_last_day'] == 0


class TestRateLimiter:
    """Test the global rate limiter."""
    
    @pytest.mark.asyncio
    async def test_record_and_check(self):
        """Test recording requests and checking limits."""
        limiter = RateLimiter(safety_margin=0.95)
        
        # Record a request
        await limiter.record_request("model-a", tokens=100)
        
        # Check limits
        allowed, reason, usage = await limiter.check_rate_limits(
            "model-a",
            rpm_limit=10,
            tpm_limit=1000
        )
        
        assert allowed
        assert usage['requests_last_minute'] == 1
        assert usage['tokens_last_minute'] == 100
    
    @pytest.mark.asyncio
    async def test_multiple_models(self):
        """Test tracking multiple models independently."""
        limiter = RateLimiter(safety_margin=0.95)
        
        # Record requests for different models
        await limiter.record_request("model-a", tokens=100)
        await limiter.record_request("model-b", tokens=200)
        await limiter.record_request("model-a", tokens=150)
        
        # Check model-a usage
        usage_a = await limiter.get_usage_stats("model-a")
        assert usage_a['requests_last_minute'] == 2
        assert usage_a['tokens_last_minute'] == 250
        
        # Check model-b usage
        usage_b = await limiter.get_usage_stats("model-b")
        assert usage_b['requests_last_minute'] == 1
        assert usage_b['tokens_last_minute'] == 200
    
    @pytest.mark.asyncio
    async def test_rpm_limit_enforcement(self):
        """Test that RPM limits block requests."""
        limiter = RateLimiter(safety_margin=0.95)
        
        # Fill up to 95% of limit (9.5 requests)
        for i in range(10):
            await limiter.record_request("model-x", tokens=10)
        
        # Should be blocked now
        allowed, reason, usage = await limiter.check_rate_limits(
            "model-x",
            rpm_limit=10
        )
        
        assert not allowed
        assert "RPM limit" in reason
        assert usage['requests_last_minute'] == 10
    
    @pytest.mark.asyncio
    async def test_tpm_limit_enforcement(self):
        """Test that TPM limits block requests."""
        limiter = RateLimiter(safety_margin=0.95)
        
        # Add tokens up to 95% of limit
        await limiter.record_request("model-y", tokens=950)
        
        # Should be blocked now
        allowed, reason, usage = await limiter.check_rate_limits(
            "model-y",
            tpm_limit=1000
        )
        
        assert not allowed
        assert "TPM limit" in reason
        assert usage['tokens_last_minute'] == 950
    
    @pytest.mark.asyncio
    async def test_estimated_tokens_projection(self):
        """Test projected TPM with estimated tokens."""
        limiter = RateLimiter(safety_margin=0.95)
        
        # Current usage: 900 tokens
        await limiter.record_request("model-z", tokens=900)
        
        # Check with estimated 100 more tokens (would exceed 95% of 1000)
        allowed, reason, usage = await limiter.check_rate_limits(
            "model-z",
            tpm_limit=1000,
            estimated_tokens=100
        )
        
        assert not allowed
        assert "Projected TPM" in reason
    
    @pytest.mark.asyncio
    async def test_daily_limit_enforcement(self):
        """Test that daily limits work."""
        limiter = RateLimiter(safety_margin=0.95)
        
        # Add requests up to daily limit
        for i in range(100):
            await limiter.record_request("model-daily", tokens=10)
        
        # Should be blocked at 95% of 100
        allowed, reason, usage = await limiter.check_rate_limits(
            "model-daily",
            rpd_limit=100
        )
        
        assert not allowed
        assert "RPD limit" in reason
        assert usage['requests_last_day'] == 100
    
    @pytest.mark.asyncio
    async def test_safety_margin(self):
        """Test that safety margin works correctly."""
        # 90% safety margin
        limiter = RateLimiter(safety_margin=0.90)
        
        # Add 9 requests (90% of 10)
        for i in range(9):
            await limiter.record_request("model-margin", tokens=10)
        
        # Should be blocked at 90%
        allowed, reason, usage = await limiter.check_rate_limits(
            "model-margin",
            rpm_limit=10
        )
        
        assert not allowed
        assert "RPM limit" in reason


@pytest.mark.asyncio
async def test_concurrent_access():
    """Test thread-safety with concurrent requests."""
    limiter = RateLimiter(safety_margin=0.95)
    
    async def add_requests():
        for i in range(10):
            await limiter.record_request("concurrent-model", tokens=50)
    
    # Run multiple concurrent tasks
    await asyncio.gather(
        add_requests(),
        add_requests(),
        add_requests()
    )
    
    usage = await limiter.get_usage_stats("concurrent-model")
    assert usage['requests_last_minute'] == 30
    assert usage['tokens_last_minute'] == 1500


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
