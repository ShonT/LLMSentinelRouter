"""
Unit tests for the dashboard aggregation functions.
"""
import pytest
import time
from unittest.mock import patch
from sentinelrouter.sentinelrouter.dashboard import (
    aggregate_metrics_by_minute,
    prepare_line_chart_data,
)


class TestAggregateMetricsByMinute:
    """Tests for aggregate_metrics_by_minute function."""

    def test_empty_metrics(self):
        """Test with empty metrics list."""
        result = aggregate_metrics_by_minute([])
        assert result == {}

    def test_non_latency_metrics_ignored(self):
        """Test that metrics of non‑latency types are ignored."""
        metrics = [
            {"timestamp": time.time(), "type": "judge_skip", "latency_ms": 100},
            {"timestamp": time.time(), "type": "fallback", "latency_ms": 200},
        ]
        result = aggregate_metrics_by_minute(metrics)
        assert result == {}

    def test_single_latency_metric(self):
        """Test a single latency metric within window."""
        current_time = time.time()
        metric = {
            "timestamp": current_time - 30,  # 30 seconds ago → minute offset 0
            "type": "judge_latency",
            "latency_ms": 150.0,
        }
        result = aggregate_metrics_by_minute([metric])
        assert len(result) == 1
        assert 0 in result
        assert result[0]["judge_latency"] == 150.0
        # Other types should not be present
        assert "weak_model_latency" not in result[0]
        assert "strong_model_latency" not in result[0]
        assert "overall_request_latency" not in result[0]

    def test_metric_outside_window(self):
        """Test metric older than window is ignored."""
        current_time = time.time()
        metric = {
            "timestamp": current_time - 300 * 60,  # 300 minutes ago
            "type": "judge_latency",
            "latency_ms": 150.0,
        }
        result = aggregate_metrics_by_minute([metric])
        assert result == {}

    @patch("time.time")
    def test_metric_on_window_boundary(self, mock_time):
        """Test metric exactly at window edge (240 minutes)."""
        current_time = 1600000000.0
        mock_time.return_value = current_time
        metric = {
            "timestamp": current_time - 240 * 60,
            "type": "weak_model_latency",
            "latency_ms": 200.0,
        }
        result = aggregate_metrics_by_minute([metric])
        # Should be assigned to offset 239 (since age_seconds = 240*60, minute_offset = 239)
        assert len(result) == 1
        assert 239 in result
        assert result[239]["weak_model_latency"] == 200.0

    def test_multiple_metrics_same_minute(self):
        """Test averaging of multiple metrics in the same minute."""
        current_time = time.time()
        metrics = [
            {
                "timestamp": current_time - 45,
                "type": "judge_latency",
                "latency_ms": 100,
            },
            {
                "timestamp": current_time - 50,
                "type": "judge_latency",
                "latency_ms": 200,
            },
            {
                "timestamp": current_time - 55,
                "type": "judge_latency",
                "latency_ms": 300,
            },
        ]
        result = aggregate_metrics_by_minute(metrics)
        assert len(result) == 1
        assert 0 in result
        assert result[0]["judge_latency"] == 200.0  # (100+200+300)/3

    def test_multiple_metric_types_same_minute(self):
        """Test different metric types aggregated separately."""
        current_time = time.time()
        metrics = [
            {
                "timestamp": current_time - 30,
                "type": "judge_latency",
                "latency_ms": 100,
            },
            {
                "timestamp": current_time - 30,
                "type": "weak_model_latency",
                "latency_ms": 250,
            },
            {
                "timestamp": current_time - 30,
                "type": "strong_model_latency",
                "latency_ms": 500,
            },
            {
                "timestamp": current_time - 30,
                "type": "overall_request_latency",
                "latency_ms": 350,
            },
        ]
        result = aggregate_metrics_by_minute(metrics)
        assert len(result) == 1
        bucket = result[0]
        assert bucket["judge_latency"] == 100.0
        assert bucket["weak_model_latency"] == 250.0
        assert bucket["strong_model_latency"] == 500.0
        assert bucket["overall_request_latency"] == 350.0

    def test_metrics_across_different_minutes(self):
        """Test metrics spread across different minute offsets."""
        current_time = time.time()
        metrics = [
            # offset 0 (0-59 seconds ago)
            {
                "timestamp": current_time - 10,
                "type": "judge_latency",
                "latency_ms": 100,
            },
            # offset 1 (60-119 seconds ago)
            {
                "timestamp": current_time - 90,
                "type": "judge_latency",
                "latency_ms": 200,
            },
            # offset 2 (120-179 seconds ago)
            {
                "timestamp": current_time - 150,
                "type": "judge_latency",
                "latency_ms": 300,
            },
        ]
        result = aggregate_metrics_by_minute(metrics)
        assert len(result) == 3
        assert result[0]["judge_latency"] == 100.0
        assert result[1]["judge_latency"] == 200.0
        assert result[2]["judge_latency"] == 300.0

    def test_missing_latency_field(self):
        """Test metric with missing latency_ms is ignored."""
        current_time = time.time()
        metric = {
            "timestamp": current_time - 30,
            "type": "judge_latency",
            # no latency_ms
        }
        result = aggregate_metrics_by_minute([metric])
        assert result == {}

    def test_custom_window_size(self):
        """Test aggregation with custom window size."""
        current_time = time.time()
        metric = {
            "timestamp": current_time
            - 90,  # 1.5 minutes ago → offset 1 in 3‑minute window
            "type": "judge_latency",
            "latency_ms": 123.0,
        }
        result = aggregate_metrics_by_minute([metric], window_minutes=3)
        # 3‑minute window: offsets 0,1,2
        assert len(result) == 1
        assert 1 in result  # minute offset 1
        assert result[1]["judge_latency"] == 123.0


class TestPrepareLineChartData:
    """Tests for prepare_line_chart_data function."""

    def test_empty_aggregated_data(self):
        """Test with empty aggregated data."""
        result = prepare_line_chart_data({})
        # Labels should be "239", "238", ..., "0" (240 minutes ago to now)
        assert result["labels"] == [str(i) for i in range(239, -1, -1)]
        assert all(v is None for v in result["judge_latency"])
        assert all(v is None for v in result["weak_model_latency"])
        assert all(v is None for v in result["strong_model_latency"])
        assert all(v is None for v in result["overall_request_latency"])

    def test_single_minute_data(self):
        """Test with data for a single minute offset."""
        aggregated = {
            0: {  # most recent minute
                "judge_latency": 150.0,
                "weak_model_latency": 250.0,
            }
        }
        result = prepare_line_chart_data(aggregated)
        # labels: 240 ... 1 (no "0"? Wait, the function creates labels from window_minutes to 0? Let's examine.
        # In the function, labels = [str(window_minutes - i - 1) for i in range(window_minutes)]
        # With window_minutes=240, labels become ["239", "238", ..., "0"]? Actually:
        # i=0 -> "239", i=239 -> "0". So labels are "239" to "0". That's 240 labels.
        # The offset 0 corresponds to the most recent minute, which should be at the last label "0".
        # Let's verify by checking the last label.
        assert result["labels"][-1] == "0"
        # The data for offset 0 should be placed at the last position (index 239).
        assert result["judge_latency"][-1] == 150.0
        assert result["weak_model_latency"][-1] == 250.0
        assert result["strong_model_latency"][-1] is None
        assert result["overall_request_latency"][-1] is None
        # All other positions should be None.
        assert result["judge_latency"][:-1] == [None] * 239
        assert result["weak_model_latency"][:-1] == [None] * 239

    def test_multiple_minutes_data(self):
        """Test with data for multiple minute offsets."""
        aggregated = {
            0: {"judge_latency": 100.0},
            1: {"judge_latency": 200.0},
            2: {"judge_latency": 300.0},
        }
        result = prepare_line_chart_data(aggregated)
        # offsets: 0 -> label "0" (index 239), 1 -> label "1" (index 238), 2 -> label "2" (index 237)
        assert result["labels"][239] == "0"
        assert result["labels"][238] == "1"
        assert result["labels"][237] == "2"
        assert result["judge_latency"][239] == 100.0
        assert result["judge_latency"][238] == 200.0
        assert result["judge_latency"][237] == 300.0
        # All other judge latency entries are None.
        for i in range(237):
            assert result["judge_latency"][i] is None

    def test_all_metric_types(self):
        """Test all four metric types in the same minute."""
        aggregated = {
            10: {
                "judge_latency": 50.0,
                "weak_model_latency": 100.0,
                "strong_model_latency": 200.0,
                "overall_request_latency": 150.0,
            }
        }
        result = prepare_line_chart_data(aggregated)
        # offset 10 corresponds to label "10"? Wait, mapping: offset 10 -> chart_index = 240-1-10 = 229.
        # label at index 229 should be "10"? Let's compute: labels are from 239 down to 0.
        # So index 229 corresponds to label "10"? Actually:
        # labels[0] = "239", labels[1] = "238", ..., labels[229] = "10"? Let's verify by checking.
        # We'll trust the function's mapping.
        idx = 240 - 1 - 10  # 229
        assert result["labels"][idx] == "10"
        assert result["judge_latency"][idx] == 50.0
        assert result["weak_model_latency"][idx] == 100.0
        assert result["strong_model_latency"][idx] == 200.0
        assert result["overall_request_latency"][idx] == 150.0

    def test_custom_window_size(self):
        """Test with custom window minutes."""
        aggregated = {
            0: {"judge_latency": 123.0},
            1: {"weak_model_latency": 456.0},
        }
        result = prepare_line_chart_data(aggregated, window_minutes=5)
        assert len(result["labels"]) == 5
        # labels should be ["4","3","2","1","0"]
        expected_labels = ["4", "3", "2", "1", "0"]
        assert result["labels"] == expected_labels
        # offset 0 -> index 4 (last), offset 1 -> index 3
        assert result["judge_latency"][4] == 123.0
        assert result["weak_model_latency"][3] == 456.0
        # other entries None
        assert result["judge_latency"][:4] == [None] * 4
        assert (
            result["weak_model_latency"][:3] + result["weak_model_latency"][4:]
            == [None] * 4
        )

    def test_out_of_range_offset_ignored(self):
        """Test that offsets outside window are ignored."""
        aggregated = {
            0: {"judge_latency": 100.0},
            300: {"judge_latency": 999.0},  # beyond default window 240
        }
        result = prepare_line_chart_data(aggregated)
        # only offset 0 should appear
        assert result["judge_latency"][-1] == 100.0
        assert result["judge_latency"].count(None) == 239

    def test_integration_with_aggregate(self):
        """Integration test: chain aggregate and prepare functions."""
        current_time = time.time()
        metrics = [
            {
                "timestamp": current_time - 30,
                "type": "judge_latency",
                "latency_ms": 100,
            },
            {
                "timestamp": current_time - 30,
                "type": "weak_model_latency",
                "latency_ms": 200,
            },
            {
                "timestamp": current_time - 90,
                "type": "judge_latency",
                "latency_ms": 150,
            },
            {
                "timestamp": current_time - 150,
                "type": "strong_model_latency",
                "latency_ms": 500,
            },
        ]
        aggregated = aggregate_metrics_by_minute(metrics)
        chart_data = prepare_line_chart_data(aggregated)
        # Verify we have three minutes with data
        assert len([x for x in chart_data["judge_latency"] if x is not None]) == 2
        assert len([x for x in chart_data["weak_model_latency"] if x is not None]) == 1
        assert (
            len([x for x in chart_data["strong_model_latency"] if x is not None]) == 1
        )
        # Check ordering: offset 0 (most recent) -> label "0", offset 1 -> label "1", offset 2 -> label "2"
        # We'll just ensure the data arrays have the correct length.
        assert len(chart_data["judge_latency"]) == 240
        assert len(chart_data["labels"]) == 240


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
