package metrics

import (
	"path/filepath"
	"testing"
)

func TestRecordAndRecent(t *testing.T) {
	c := NewCollector(filepath.Join(t.TempDir(), "test.jsonl"))

	c.Record("judge_latency", map[string]any{"latency_ms": 42.0, "session_id": "s1"})
	c.Record("weak_model_latency", map[string]any{"latency_ms": 100.0, "session_id": "s1"})

	recent := c.Recent(10)
	if len(recent) != 2 {
		t.Fatalf("recent = %d, want 2", len(recent))
	}
	if recent[0]["type"] != "judge_latency" {
		t.Fatalf("type = %q", recent[0]["type"])
	}
	if recent[0]["latency_ms"] != 42.0 {
		t.Fatalf("latency = %v", recent[0]["latency_ms"])
	}
}

func TestRecentLimitsOutput(t *testing.T) {
	c := NewCollector(filepath.Join(t.TempDir(), "test.jsonl"))
	for i := 0; i < 20; i++ {
		c.Record("event", map[string]any{"i": i})
	}

	recent := c.Recent(5)
	if len(recent) != 5 {
		t.Fatalf("recent = %d, want 5", len(recent))
	}
}

func TestCollectorLimit(t *testing.T) {
	c := NewCollector(filepath.Join(t.TempDir(), "test.jsonl"))
	c.limit = 10

	for i := 0; i < 20; i++ {
		c.Record("event", map[string]any{"i": i})
	}
	if len(c.recent) > 10 {
		t.Fatalf("recent len = %d, want <= 10", len(c.recent))
	}
}

func TestDashboardAggregateWithMetrics(t *testing.T) {
	c := NewCollector(filepath.Join(t.TempDir(), "test.jsonl"))

	c.Record("judge_latency", map[string]any{"latency_ms": 10.0, "judge_id": "j1"})
	c.Record("judge_latency", map[string]any{"latency_ms": 20.0, "judge_id": "j1"})
	c.Record("judge_skip", map[string]any{"reason": "semantic_cache"})
	c.Record("judge_skip", map[string]any{"reason": "request_disabled"})
	c.Record("weak_model_latency", map[string]any{"latency_ms": 50.0, "model_id": "m1"})
	c.Record("strong_model_latency", map[string]any{"latency_ms": 200.0, "model_id": "m2"})
	c.Record("overall_request_latency", map[string]any{"latency_ms": 250.0})

	agg := c.DashboardAggregate(10000)

	if agg.JudgeCallCount != 2 {
		t.Fatalf("judge_call_count = %d, want 2", agg.JudgeCallCount)
	}
	if agg.JudgeSkipCount != 2 {
		t.Fatalf("judge_skip_count = %d, want 2", agg.JudgeSkipCount)
	}
	if agg.JudgeLatency.Count != 2 {
		t.Fatalf("judge latency count = %d, want 2", agg.JudgeLatency.Count)
	}
	if agg.JudgeLatency.AvgMS != 15.0 {
		t.Fatalf("judge avg = %g, want 15", agg.JudgeLatency.AvgMS)
	}
	if agg.WeakModelLatency.Count != 1 {
		t.Fatalf("weak latency count = %d, want 1", agg.WeakModelLatency.Count)
	}
	if agg.StrongModelLatency.Count != 1 {
		t.Fatalf("strong latency count = %d, want 1", agg.StrongModelLatency.Count)
	}
	if agg.JudgeBreakdown["semantic_cache"] != 1 {
		t.Fatalf("breakdown = %+v", agg.JudgeBreakdown)
	}
	if agg.JudgeBreakdown["request_disabled"] != 1 {
		t.Fatalf("breakdown = %+v", agg.JudgeBreakdown)
	}
}

func TestDashboardAggregateEmpty(t *testing.T) {
	c := NewCollector(filepath.Join(t.TempDir(), "test.jsonl"))
	agg := c.DashboardAggregate(10000)

	if agg.JudgeCallCount != 0 {
		t.Fatalf("judge_call_count = %d", agg.JudgeCallCount)
	}
	if agg.JudgeSkipRate != 0 {
		t.Fatalf("judge_skip_rate = %g", agg.JudgeSkipRate)
	}
}

func TestDashboardAggregateFallbackCount(t *testing.T) {
	c := NewCollector(filepath.Join(t.TempDir(), "test.jsonl"))
	c.Record("weak_model_fallback", map[string]any{"model_id": "m1"})
	c.Record("strong_model_fallback", map[string]any{"model_id": "m2"})

	agg := c.DashboardAggregate(10000)
	if agg.TotalFallbacks != 2 {
		t.Fatalf("total_fallbacks = %d, want 2", agg.TotalFallbacks)
	}
}

func TestReset(t *testing.T) {
	c := NewCollector(filepath.Join(t.TempDir(), "test.jsonl"))
	c.Record("event", nil)
	c.Record("event", nil)

	_ = c.Reset()
	recent := c.Recent(10)
	if len(recent) != 0 {
		t.Fatalf("recent = %d after reset", len(recent))
	}
}
