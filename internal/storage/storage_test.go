package storage

import (
	"context"
	"database/sql"
	"testing"
	"time"
)

func openTestStore(t *testing.T) *Store {
	t.Helper()
	store, err := Open(context.Background(), "sqlite:///"+t.TempDir()+"/test.db")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	t.Cleanup(func() { _ = store.Close() })
	return store
}

func TestOpenAndInitCreatesAllTables(t *testing.T) {
	store := openTestStore(t)
	ctx := context.Background()

	tables := []string{"sessions", "routing_decisions", "cycle_detection", "escalation_log",
		"semantic_cache_entries", "semantic_cache_stats", "escalation_traces", "app_state"}
	for _, table := range tables {
		var count int
		err := store.db.QueryRowContext(ctx, "SELECT COUNT(*) FROM "+table).Scan(&count)
		if err != nil {
			t.Fatalf("table %s does not exist: %v", table, err)
		}
	}
}

func TestGetOrCreateSessionCreatesAndReturns(t *testing.T) {
	store := openTestStore(t)
	ctx := context.Background()

	session, err := store.GetOrCreateSession(ctx, "test-sess", "10.0.0.1", "free", 10.0)
	if err != nil {
		t.Fatalf("create: %v", err)
	}
	if session.SessionID != "test-sess" {
		t.Fatalf("session_id = %q", session.SessionID)
	}
	if session.MaxCostPerSession != 10.0 {
		t.Fatalf("max_cost = %g", session.MaxCostPerSession)
	}

	existing, err := store.GetOrCreateSession(ctx, "test-sess", "", "", 99.0)
	if err != nil {
		t.Fatalf("get existing: %v", err)
	}
	if existing.MaxCostPerSession != 10.0 {
		t.Fatalf("max_cost changed on re-get: %g", existing.MaxCostPerSession)
	}
}

func TestGetSessionNotFound(t *testing.T) {
	store := openTestStore(t)
	_, found, err := store.GetSession(context.Background(), "nonexistent")
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	if found {
		t.Fatal("should not find nonexistent session")
	}
}

func TestTryReserveBudgetAtomicConditional(t *testing.T) {
	store := openTestStore(t)
	ctx := context.Background()
	_, _ = store.GetOrCreateSession(ctx, "budget-sess", "", "free", 10.0)

	ok, err := store.TryReserveBudget(ctx, "budget-sess", 8.0)
	if err != nil {
		t.Fatalf("reserve: %v", err)
	}
	if !ok {
		t.Fatal("should succeed with 8/10 budget")
	}

	ok, err = store.TryReserveBudget(ctx, "budget-sess", 5.0)
	if err != nil {
		t.Fatalf("second reserve: %v", err)
	}
	if ok {
		t.Fatal("should fail exceeding 10.0 limit")
	}
}

func TestReserveBudgetWithRetries(t *testing.T) {
	store := openTestStore(t)
	ctx := context.Background()
	_, _ = store.GetOrCreateSession(ctx, "retry-sess", "", "free", 10.0)

	ok, err := store.ReserveBudget(ctx, "retry-sess", 8.0, 3)
	if err != nil {
		t.Fatalf("reserve: %v", err)
	}
	if !ok {
		t.Fatal("should succeed")
	}

	ok, err = store.ReserveBudget(ctx, "retry-sess", 5.0, 3)
	if err != nil {
		t.Fatalf("second reserve: %v", err)
	}
	if ok {
		t.Fatal("should fail as budget exceeded")
	}
}

func TestAdjustReservedCost(t *testing.T) {
	store := openTestStore(t)
	ctx := context.Background()
	_, _ = store.GetOrCreateSession(ctx, "adjust-sess", "", "free", 20.0)
	_, _ = store.TryReserveBudget(ctx, "adjust-sess", 10.0)

	err := store.AdjustReservedCost(ctx, "adjust-sess", 10.0, 3.0)
	if err != nil {
		t.Fatalf("adjust: %v", err)
	}
	session, _, _ := store.GetSession(ctx, "adjust-sess")
	if session.CurrentCost < 2.9 || session.CurrentCost > 3.1 {
		t.Fatalf("current_cost = %g, want ~3.0", session.CurrentCost)
	}
}

func TestAddCost(t *testing.T) {
	store := openTestStore(t)
	ctx := context.Background()
	_, _ = store.GetOrCreateSession(ctx, "cost-sess", "", "free", 10.0)

	_ = store.AddCost(ctx, "cost-sess", 2.5)
	_ = store.AddCost(ctx, "cost-sess", 1.5)
	session, _, _ := store.GetSession(ctx, "cost-sess")
	if session.CurrentCost != 4.0 {
		t.Fatalf("current_cost = %g, want 4.0", session.CurrentCost)
	}
}

func TestResetSession(t *testing.T) {
	store := openTestStore(t)
	ctx := context.Background()
	_, _ = store.GetOrCreateSession(ctx, "reset-sess", "", "free", 10.0)
	_ = store.AddCost(ctx, "reset-sess", 5.0)

	_ = store.ResetSession(ctx, "reset-sess", 20.0)
	session, _, _ := store.GetSession(ctx, "reset-sess")
	if session.CurrentCost != 0 {
		t.Fatalf("current_cost = %g, want 0", session.CurrentCost)
	}
	if session.MaxCostPerSession != 20.0 {
		t.Fatalf("max_cost = %g, want 20", session.MaxCostPerSession)
	}
}

func TestDeactivateSession(t *testing.T) {
	store := openTestStore(t)
	ctx := context.Background()
	_, _ = store.GetOrCreateSession(ctx, "deactivate-sess", "", "free", 10.0)

	_ = store.DeactivateSession(ctx, "deactivate-sess")
	session, found, _ := store.GetSession(ctx, "deactivate-sess")
	if !found {
		t.Fatal("should find deactivated session")
	}
	if session.IsActive {
		t.Fatal("session should be inactive")
	}
}

func TestInsertAndQueryRoutingDecisions(t *testing.T) {
	store := openTestStore(t)
	ctx := context.Background()
	_, _ = store.GetOrCreateSession(ctx, "decision-sess", "", "free", 10.0)

	err := store.InsertRoutingDecision(ctx, RoutingDecision{
		SessionID:       "decision-sess",
		RequestID:       "req-1",
		Timestamp:       time.Now().UTC(),
		ModelUsed:       "model-a",
		ComplexityScore: 0.5,
		CostIncurred:    0.01,
		CostSource:      "provider",
		PromptHash:      "abc123",
		ImpactScope:     sql.NullString{String: "LOW", Valid: true},
		Reason:          sql.NullString{String: "test", Valid: true},
	})
	if err != nil {
		t.Fatalf("insert: %v", err)
	}

	decisions, err := store.RoutingDecisionsBySession(ctx, "decision-sess")
	if err != nil {
		t.Fatalf("query: %v", err)
	}
	if len(decisions) != 1 {
		t.Fatalf("decisions = %d, want 1", len(decisions))
	}
	if decisions[0].ModelUsed != "model-a" {
		t.Fatalf("model = %q", decisions[0].ModelUsed)
	}
}

func TestRecentRoutingDecisions(t *testing.T) {
	store := openTestStore(t)
	ctx := context.Background()
	_, _ = store.GetOrCreateSession(ctx, "recent-sess", "", "free", 10.0)

	for i := 0; i < 5; i++ {
		_ = store.InsertRoutingDecision(ctx, RoutingDecision{
			SessionID: "recent-sess",
			RequestID: "req-" + string(rune('A'+i)),
			Timestamp: time.Now().UTC(),
			ModelUsed: "model",
		})
	}

	recent, err := store.RecentRoutingDecisions(ctx, 3)
	if err != nil {
		t.Fatalf("query: %v", err)
	}
	if len(recent) != 3 {
		t.Fatalf("recent = %d, want 3", len(recent))
	}
}

func TestClearRoutingDecisions(t *testing.T) {
	store := openTestStore(t)
	ctx := context.Background()
	_, _ = store.GetOrCreateSession(ctx, "clear-sess", "", "free", 10.0)
	_ = store.InsertRoutingDecision(ctx, RoutingDecision{
		SessionID: "clear-sess", RequestID: "req-x", Timestamp: time.Now().UTC(), ModelUsed: "m",
	})

	_ = store.ClearRoutingDecisions(ctx)
	decisions, _ := store.RecentRoutingDecisions(ctx, 100)
	if len(decisions) != 0 {
		t.Fatalf("decisions = %d after clear", len(decisions))
	}
}

func TestMetricsSummary(t *testing.T) {
	store := openTestStore(t)
	ctx := context.Background()
	_, _ = store.GetOrCreateSession(ctx, "metrics-sess", "", "free", 10.0)
	_ = store.AddCost(ctx, "metrics-sess", 2.0)

	strong := map[string]bool{"strong-model": true}
	_ = store.InsertRoutingDecision(ctx, RoutingDecision{
		SessionID: "metrics-sess", RequestID: "req-w", Timestamp: time.Now().UTC(), ModelUsed: "weak-model",
	})
	_ = store.InsertRoutingDecision(ctx, RoutingDecision{
		SessionID: "metrics-sess", RequestID: "req-s", Timestamp: time.Now().UTC(), ModelUsed: "strong-model",
	})

	summary, err := store.MetricsSummary(ctx, strong)
	if err != nil {
		t.Fatalf("summary: %v", err)
	}
	if summary.RequestsTotal != 2 {
		t.Fatalf("requests = %d, want 2", summary.RequestsTotal)
	}
	if summary.StrongRequests != 1 {
		t.Fatalf("strong = %d, want 1", summary.StrongRequests)
	}
	if summary.WeakRequests != 1 {
		t.Fatalf("weak = %d, want 1", summary.WeakRequests)
	}
	if summary.EscalationRate != 0.5 {
		t.Fatalf("escalation_rate = %g, want 0.5", summary.EscalationRate)
	}
}

func TestSaveAndLoadState(t *testing.T) {
	store := openTestStore(t)
	ctx := context.Background()

	type testState struct {
		Name  string `json:"name"`
		Value int    `json:"value"`
	}
	err := store.SaveState(ctx, "test_key", testState{Name: "hello", Value: 42})
	if err != nil {
		t.Fatalf("save: %v", err)
	}

	var loaded testState
	ok, err := store.LoadState(ctx, "test_key", &loaded)
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if !ok {
		t.Fatal("should find saved state")
	}
	if loaded.Name != "hello" || loaded.Value != 42 {
		t.Fatalf("loaded = %+v", loaded)
	}

	ok, _ = store.LoadState(ctx, "missing_key", &loaded)
	if ok {
		t.Fatal("should not find missing key")
	}
}

func TestInsertCycleDetection(t *testing.T) {
	store := openTestStore(t)
	ctx := context.Background()
	_, _ = store.GetOrCreateSession(ctx, "cycle-sess", "", "free", 10.0)

	err := store.InsertCycleDetection(ctx, CycleDetectionRecord{
		SessionID:    "cycle-sess",
		PromptHash:   "ph1",
		ResponseHash: "rh1",
	})
	if err != nil {
		t.Fatalf("insert cycle: %v", err)
	}
}

func TestInsertEscalationLog(t *testing.T) {
	store := openTestStore(t)
	ctx := context.Background()
	_, _ = store.GetOrCreateSession(ctx, "esc-sess", "", "free", 10.0)

	err := store.InsertEscalationLog(ctx, EscalationLogRecord{
		SessionID:       "esc-sess",
		EscalationRate:  0.1,
		ThresholdBefore: 0.7,
		ThresholdAfter:  0.65,
		Reason:          "dynamic_threshold_adjusted",
	})
	if err != nil {
		t.Fatalf("insert escalation log: %v", err)
	}
}

func TestInsertEscalationTrace(t *testing.T) {
	store := openTestStore(t)
	ctx := context.Background()
	_, _ = store.GetOrCreateSession(ctx, "trace-sess", "", "free", 10.0)

	err := store.InsertEscalationTrace(ctx, EscalationTraceRecord{
		SessionID:       "trace-sess",
		RequestID:       "req-t1",
		ModelUsed:       "strong-model",
		ComplexityScore: 0.9,
		ImpactScope:     sql.NullString{String: "HIGH", Valid: true},
		Reason:          sql.NullString{String: "complexity exceeds threshold", Valid: true},
	})
	if err != nil {
		t.Fatalf("insert trace: %v", err)
	}
}

func TestSemanticCacheStatsRoundTrip(t *testing.T) {
	store := openTestStore(t)
	ctx := context.Background()

	err := store.UpsertSemanticCacheStats(ctx, SemanticCacheStats{
		SemanticHash: "hash-1",
		TotalCalls:   5,
		WeakCalls:    3,
		StrongCalls:  2,
		TotalCost:    0.05,
		TotalTokens:  100,
		LastCalledAt: time.Now().UTC(),
		FirstSeenAt:  time.Now().UTC(),
	})
	if err != nil {
		t.Fatalf("upsert: %v", err)
	}

	stats, err := store.LoadSemanticCacheStats(ctx)
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if len(stats) != 1 {
		t.Fatalf("stats = %d, want 1", len(stats))
	}
	if stats["hash-1"].TotalCalls != 5 {
		t.Fatalf("total_calls = %d", stats["hash-1"].TotalCalls)
	}
}

func TestSemanticCacheSummary(t *testing.T) {
	store := openTestStore(t)
	ctx := context.Background()

	_ = store.UpsertSemanticCacheStats(ctx, SemanticCacheStats{
		SemanticHash: "h1", TotalCalls: 5, WeakCalls: 3, StrongCalls: 2,
		LastCalledAt: time.Now().UTC(), FirstSeenAt: time.Now().UTC(),
	})
	_ = store.UpsertSemanticCacheStats(ctx, SemanticCacheStats{
		SemanticHash: "h2", TotalCalls: 0, WeakCalls: 0, StrongCalls: 0,
		LastCalledAt: time.Now().UTC(), FirstSeenAt: time.Now().UTC(),
	})

	hits, misses, clusters, err := store.SemanticCacheSummary(ctx)
	if err != nil {
		t.Fatalf("summary: %v", err)
	}
	if clusters != 2 {
		t.Fatalf("clusters = %d, want 2", clusters)
	}
	if hits != 1 {
		t.Fatalf("hits = %d, want 1", hits)
	}
	if misses != 1 {
		t.Fatalf("misses = %d, want 1", misses)
	}
}

func TestClearSemanticCacheStats(t *testing.T) {
	store := openTestStore(t)
	ctx := context.Background()

	_ = store.UpsertSemanticCacheStats(ctx, SemanticCacheStats{
		SemanticHash: "h1", LastCalledAt: time.Now().UTC(), FirstSeenAt: time.Now().UTC(),
	})
	_ = store.InsertSemanticCacheEntry(ctx, SemanticCacheEntry{
		SemanticHash: "h1", PromptPreview: "test",
	})

	_ = store.ClearSemanticCacheStats(ctx)
	stats, _ := store.LoadSemanticCacheStats(ctx)
	if len(stats) != 0 {
		t.Fatalf("stats = %d after clear", len(stats))
	}
}

func TestDataDir(t *testing.T) {
	dir := DataDir("")
	if dir != "." && dir != "./data" && dir != "data" {
		t.Fatalf("DataDir empty = %q, want data directory", dir)
	}
	dir = DataDir("sqlite:///tmp/test.db")
	if dir != "/tmp" && dir != "tmp" {
		t.Fatalf("DataDir absolute = %q, want /tmp or tmp", dir)
	}
}
