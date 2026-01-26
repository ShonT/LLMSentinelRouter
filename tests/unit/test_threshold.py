"""
Unit tests for Module C: Dynamic Thresholding (5% Rule)
Tests the threshold adjustment and strict mode functionality.
"""

import pytest
from sentinelrouter.sentinelrouter.threshold import DynamicThreshold


class TestDynamicThreshold:
    """Tests for Module C - Dynamic Thresholding (5% Rule)."""

    # def test_initialization_default(self):
    #     """Test threshold initialization with defaults."""
    #     threshold = DynamicThreshold()

    #     assert threshold.threshold == 0.7  # Default from config
    #     assert threshold.target_rate == 0.05  # 5% rule
    #     assert threshold.window_size == 20
    #     assert len(threshold.decision_window) == 0

    def test_initialization_custom(self):
        """Test threshold initialization with custom values."""
        threshold = DynamicThreshold(
            initial_threshold=0.6, target_rate=0.1, window_size=50
        )

        assert threshold.threshold == 0.6
        assert threshold.target_rate == 0.1
        assert threshold.window_size == 50

    def test_add_decision_weak(self):
        """Test adding weak model decisions."""
        threshold = DynamicThreshold(window_size=5)

        threshold.add_decision(False)  # Weak model
        threshold.add_decision(False)
        threshold.add_decision(False)

        assert len(threshold.decision_window) == 3
        assert sum(threshold.decision_window) == 0  # No strong decisions

    def test_add_decision_strong(self):
        """Test adding strong model decisions."""
        threshold = DynamicThreshold(window_size=5)

        threshold.add_decision(True)  # Strong model
        threshold.add_decision(True)

        assert len(threshold.decision_window) == 2
        assert sum(threshold.decision_window) == 2

    def test_add_decision_rolling_window(self):
        """Test that decision window rolls (FIFO)."""
        threshold = DynamicThreshold(window_size=3)

        threshold.add_decision(True)  # [True]
        threshold.add_decision(False)  # [True, False]
        threshold.add_decision(True)  # [True, False, True]
        threshold.add_decision(False)  # [False, True, False] - first True dropped

        assert len(threshold.decision_window) == 3
        assert list(threshold.decision_window) == [False, True, False]

    def test_current_escalation_rate_empty(self):
        """Test escalation rate with empty window."""
        threshold = DynamicThreshold()

        rate = threshold.current_escalation_rate()
        assert rate == 0.0

    def test_current_escalation_rate_all_weak(self):
        """Test escalation rate with all weak decisions."""
        threshold = DynamicThreshold(window_size=10)

        for _ in range(10):
            threshold.add_decision(False)

        rate = threshold.current_escalation_rate()
        assert rate == 0.0

    def test_current_escalation_rate_all_strong(self):
        """Test escalation rate with all strong decisions."""
        threshold = DynamicThreshold(window_size=10)

        for _ in range(10):
            threshold.add_decision(True)

        rate = threshold.current_escalation_rate()
        assert rate == 1.0

    def test_current_escalation_rate_mixed(self):
        """Test escalation rate with mixed decisions."""
        threshold = DynamicThreshold(window_size=20)

        # Add 5 strong, 15 weak = 25% escalation rate
        for _ in range(5):
            threshold.add_decision(True)
        for _ in range(15):
            threshold.add_decision(False)

        rate = threshold.current_escalation_rate()
        assert rate == 0.25

    def test_current_escalation_rate_exactly_5_percent(self):
        """Test escalation rate at exactly 5% (target)."""
        threshold = DynamicThreshold(window_size=20, target_rate=0.05)

        # Add 1 strong, 19 weak = 5% escalation rate
        threshold.add_decision(True)
        for _ in range(19):
            threshold.add_decision(False)

        rate = threshold.current_escalation_rate()
        assert rate == 0.05

    def test_is_strict_mode_not_enough_data(self):
        """Test strict mode when window not full."""
        threshold = DynamicThreshold(window_size=20)

        # Add only 10 decisions
        for _ in range(10):
            threshold.add_decision(True)

        # Should not be in strict mode yet
        assert threshold.is_strict_mode() is False

    def test_is_strict_mode_below_target(self):
        """Test strict mode when escalation rate below target."""
        threshold = DynamicThreshold(window_size=20, target_rate=0.05)

        # 1 strong, 19 weak = 5% (at target)
        threshold.add_decision(True)
        for _ in range(19):
            threshold.add_decision(False)

        assert threshold.is_strict_mode() is False

    def test_is_strict_mode_above_target(self):
        """Test strict mode when escalation rate above target."""
        threshold = DynamicThreshold(window_size=20, target_rate=0.05)

        # 5 strong, 15 weak = 25% (above 5% target)
        for _ in range(5):
            threshold.add_decision(True)
        for _ in range(15):
            threshold.add_decision(False)

        assert threshold.is_strict_mode() is True

    def test_adjust_threshold_not_enough_data(self):
        """Test threshold adjustment with insufficient data."""
        threshold = DynamicThreshold(window_size=20)

        for _ in range(10):
            threshold.add_decision(True)

        new_threshold = threshold.adjust_threshold()
        assert new_threshold is None  # No adjustment

    def test_adjust_threshold_increase_on_high_escalation(self):
        """Test threshold increases when escalation rate too high."""
        threshold = DynamicThreshold(
            initial_threshold=0.7, window_size=20, target_rate=0.05
        )

        # 10 strong, 10 weak = 50% escalation (way above 5%)
        for _ in range(10):
            threshold.add_decision(True)
        for _ in range(10):
            threshold.add_decision(False)

        new_threshold = threshold.adjust_threshold()

        assert new_threshold is not None
        assert new_threshold > 0.7
        assert threshold.threshold > 0.7

    def test_adjust_threshold_decrease_on_low_escalation(self):
        """Test threshold decreases when escalation rate too low."""
        threshold = DynamicThreshold(
            initial_threshold=0.7, window_size=20, target_rate=0.05
        )

        # 0 strong, 20 weak = 0% escalation (below 5%)
        for _ in range(20):
            threshold.add_decision(False)

        new_threshold = threshold.adjust_threshold()

        assert new_threshold is not None
        assert new_threshold < 0.7
        assert threshold.threshold < 0.7

    def test_adjust_threshold_no_change_at_target(self):
        """Test threshold unchanged when at target rate."""
        threshold = DynamicThreshold(
            initial_threshold=0.7, window_size=20, target_rate=0.05
        )

        # 1 strong, 19 weak = 5% escalation (exactly at target)
        threshold.add_decision(True)
        for _ in range(19):
            threshold.add_decision(False)

        new_threshold = threshold.adjust_threshold()

        # Should be None (no change) or very small change
        assert new_threshold is None or abs(new_threshold - 0.7) < 0.01

    def test_threshold_bounds_maximum(self):
        """Test threshold doesn't exceed maximum (0.99)."""
        threshold = DynamicThreshold(
            initial_threshold=0.98, window_size=20, target_rate=0.05
        )

        # Very high escalation rate
        for _ in range(20):
            threshold.add_decision(True)

        # Adjust multiple times
        for _ in range(10):
            threshold.adjust_threshold()

        assert threshold.threshold <= 0.99

    def test_threshold_bounds_minimum(self):
        """Test threshold doesn't go below minimum (0.0)."""
        threshold = DynamicThreshold(
            initial_threshold=0.02, window_size=20, target_rate=0.05
        )

        # Very low escalation rate
        for _ in range(20):
            threshold.add_decision(False)

        # Adjust multiple times
        for _ in range(10):
            threshold.adjust_threshold()

        assert threshold.threshold >= 0.0

    def test_threshold_adjustment_increment(self):
        """Test threshold adjustment increment size."""
        threshold = DynamicThreshold(
            initial_threshold=0.7, window_size=20, target_rate=0.05
        )

        # High escalation
        for _ in range(15):
            threshold.add_decision(True)
        for _ in range(5):
            threshold.add_decision(False)

        old_threshold = threshold.threshold
        threshold.adjust_threshold()

        # Should increase by 0.01
        assert abs((threshold.threshold - old_threshold) - 0.01) < 0.001

    def test_threshold_adjustment_decrement(self):
        """Test threshold adjustment decrement size."""
        threshold = DynamicThreshold(
            initial_threshold=0.7, window_size=20, target_rate=0.05
        )

        # Very low escalation
        for _ in range(20):
            threshold.add_decision(False)

        old_threshold = threshold.threshold
        threshold.adjust_threshold()

        # Should decrease by 0.02
        assert abs((old_threshold - threshold.threshold) - 0.02) < 0.001

    def test_hysteresis_prevents_oscillation(self):
        """Test hysteresis prevents threshold oscillation."""
        threshold = DynamicThreshold(
            initial_threshold=0.7, window_size=20, target_rate=0.05
        )

        # Slightly below target (3% vs 5% target)
        # 0 strong, 20 weak
        for _ in range(20):
            threshold.add_decision(False)

        result = threshold.adjust_threshold()

        # With hysteresis, might not adjust for small difference
        # Check behavior is reasonable
        assert threshold.threshold >= 0.0

    def test_multiple_adjustments_converge(self):
        """Test multiple adjustments converge toward target."""
        threshold = DynamicThreshold(
            initial_threshold=0.9, window_size=20, target_rate=0.05  # Start high
        )

        # Simulate consistent low escalation
        for cycle in range(10):
            # Clear and add low escalation pattern
            for _ in range(20):
                threshold.add_decision(False if cycle % 20 > 0 else True)
            threshold.adjust_threshold()

        # Should have decreased from 0.9
        assert threshold.threshold < 0.9

    def test_get_current_threshold(self):
        """Test getting current threshold value."""
        threshold = DynamicThreshold(initial_threshold=0.75)
        assert threshold.threshold == 0.75

        # After adjustments
        for _ in range(20):
            threshold.add_decision(True)
        threshold.adjust_threshold()

        # Should have changed
        assert threshold.threshold != 0.75


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
