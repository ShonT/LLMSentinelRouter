package metrics

import (
	"math"
	"sort"
	"time"
)

type LatencyAggregate struct {
	AvgMS float64 `json:"avg_ms"`
	P50MS float64 `json:"p50_ms"`
	P95MS float64 `json:"p95_ms"`
	Count int     `json:"count"`
}

type DashboardAggregate struct {
	TotalFallbacks      int              `json:"total_fallbacks"`
	JudgeLatency        LatencyAggregate `json:"judge_latency"`
	WeakModelLatency    LatencyAggregate `json:"weak_model_latency"`
	StrongModelLatency  LatencyAggregate `json:"strong_model_latency"`
	LatencySeries       map[string]any   `json:"latency_series"`
	JudgeSuccessRate    float64          `json:"judge_success_rate"`
	JudgeSkipRate       float64          `json:"judge_skip_rate"`
	JudgeSkipCount      int              `json:"judge_skip_count"`
	JudgeCallCount      int              `json:"judge_call_count"`
	JudgeFallbackCount  int              `json:"judge_fallback_count"`
	JudgeBreakdown      map[string]int   `json:"judge_breakdown"`
	FallbackChain       []any            `json:"fallback_chain"`
	RecentMetricsSample []map[string]any `json:"recent_metrics_sample"`
}

func (c *Collector) DashboardAggregate(limit int) DashboardAggregate {
	metrics := c.Recent(limit)
	if limit <= 0 {
		limit = 10000
	}
	if len(metrics) > limit {
		metrics = metrics[len(metrics)-limit:]
	}
	out := DashboardAggregate{
		LatencySeries: map[string]any{
			"labels":                  []string{},
			"judge_latency":           []float64{},
			"weak_model_latency":      []float64{},
			"strong_model_latency":    []float64{},
			"overall_request_latency": []float64{},
		},
		JudgeBreakdown:      map[string]int{},
		FallbackChain:       []any{},
		RecentMetricsSample: c.Recent(50),
	}
	judgeValues := []float64{}
	weakValues := []float64{}
	strongValues := []float64{}
	overallValues := []float64{}
	seriesBuckets := map[int64]map[string][]float64{}
	var judgeCalls, judgeSkips, judgeFallbacks, fallbacks int

	for _, metric := range metrics {
		metricType, _ := metric["type"].(string)
		status, _ := metric["status"].(string)
		if status == "error" {
			continue
		}
		ts := metricTimestamp(metric)
		bucket := ts / (60 * 1000)
		if seriesBuckets[bucket] == nil {
			seriesBuckets[bucket] = map[string][]float64{}
		}
		switch metricType {
		case "judge_latency":
			if v, ok := floatMetric(metric["latency_ms"]); ok {
				judgeValues = append(judgeValues, v)
				seriesBuckets[bucket]["judge_latency"] = append(seriesBuckets[bucket]["judge_latency"], v)
				judgeCalls++
			}
		case "weak_model_latency":
			if v, ok := floatMetric(metric["latency_ms"]); ok {
				weakValues = append(weakValues, v)
				seriesBuckets[bucket]["weak_model_latency"] = append(seriesBuckets[bucket]["weak_model_latency"], v)
			}
		case "strong_model_latency":
			if v, ok := floatMetric(metric["latency_ms"]); ok {
				strongValues = append(strongValues, v)
				seriesBuckets[bucket]["strong_model_latency"] = append(seriesBuckets[bucket]["strong_model_latency"], v)
			}
		case "overall_request_latency":
			if v, ok := floatMetric(metric["latency_ms"]); ok {
				overallValues = append(overallValues, v)
				seriesBuckets[bucket]["overall_request_latency"] = append(seriesBuckets[bucket]["overall_request_latency"], v)
			}
		case "judge_skip":
			judgeSkips++
			if reason, ok := metric["reason"].(string); ok {
				out.JudgeBreakdown[reason]++
			}
		case "judge_timeout_escalation":
			judgeFallbacks++
		case "weak_model_fallback", "strong_model_fallback", "fallback":
			fallbacks++
			out.FallbackChain = append(out.FallbackChain, metric)
		}
	}
	out.TotalFallbacks = fallbacks
	out.JudgeLatency = aggregateLatency(judgeValues)
	out.WeakModelLatency = aggregateLatency(weakValues)
	out.StrongModelLatency = aggregateLatency(strongValues)
	out.JudgeCallCount = judgeCalls
	out.JudgeSkipCount = judgeSkips
	out.JudgeFallbackCount = judgeFallbacks
	if judgeCalls+judgeSkips > 0 {
		out.JudgeSkipRate = float64(judgeSkips) / float64(judgeCalls+judgeSkips)
	}
	if judgeCalls > 0 {
		out.JudgeSuccessRate = float64(judgeCalls-judgeFallbacks) / float64(judgeCalls)
	}
	labels := make([]int64, 0, len(seriesBuckets))
	for bucket := range seriesBuckets {
		labels = append(labels, bucket)
	}
	sort.Slice(labels, func(i, j int) bool { return labels[i] < labels[j] })
	labelStrings := make([]string, 0, len(labels))
	judgeSeries := make([]float64, 0, len(labels))
	weakSeries := make([]float64, 0, len(labels))
	strongSeries := make([]float64, 0, len(labels))
	overallSeries := make([]float64, 0, len(labels))
	for _, bucket := range labels {
		labelStrings = append(labelStrings, time.UnixMilli(bucket*60*1000).UTC().Format("15:04"))
		judgeSeries = append(judgeSeries, avg(seriesBuckets[bucket]["judge_latency"]))
		weakSeries = append(weakSeries, avg(seriesBuckets[bucket]["weak_model_latency"]))
		strongSeries = append(strongSeries, avg(seriesBuckets[bucket]["strong_model_latency"]))
		overallSeries = append(overallSeries, avg(seriesBuckets[bucket]["overall_request_latency"]))
	}
	out.LatencySeries["labels"] = labelStrings
	out.LatencySeries["judge_latency"] = judgeSeries
	out.LatencySeries["weak_model_latency"] = weakSeries
	out.LatencySeries["strong_model_latency"] = strongSeries
	out.LatencySeries["overall_request_latency"] = overallSeries
	_ = overallValues
	return out
}

func aggregateLatency(values []float64) LatencyAggregate {
	if len(values) == 0 {
		return LatencyAggregate{}
	}
	sorted := append([]float64(nil), values...)
	sort.Float64s(sorted)
	return LatencyAggregate{
		AvgMS: avg(sorted),
		P50MS: percentile(sorted, 0.5),
		P95MS: percentile(sorted, 0.95),
		Count: len(sorted),
	}
}

func percentile(sorted []float64, p float64) float64 {
	if len(sorted) == 0 {
		return 0
	}
	index := int(math.Round(p * float64(len(sorted)-1)))
	if index < 0 {
		index = 0
	}
	if index >= len(sorted) {
		index = len(sorted) - 1
	}
	return sorted[index]
}

func avg(values []float64) float64 {
	if len(values) == 0 {
		return 0
	}
	sum := 0.0
	for _, value := range values {
		sum += value
	}
	return sum / float64(len(values))
}

func floatMetric(value any) (float64, bool) {
	switch v := value.(type) {
	case float64:
		return v, true
	case int:
		return float64(v), true
	case int64:
		return float64(v), true
	default:
		return 0, false
	}
}

func metricTimestamp(metric map[string]any) int64 {
	switch v := metric["timestamp"].(type) {
	case float64:
		return int64(v)
	case int64:
		return v
	default:
		return time.Now().UnixMilli()
	}
}
