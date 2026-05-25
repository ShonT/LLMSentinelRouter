package budget

import (
	"context"
	"testing"

	"github.com/ShonT/LLMSentinelRouter/internal/storage"
)

func openTestStore(t *testing.T) *storage.Store {
	t.Helper()
	store, err := storage.Open(context.Background(), "sqlite:///"+t.TempDir()+"/test.db")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	t.Cleanup(func() { _ = store.Close() })
	return store
}

func TestGetOrCreateSession(t *testing.T) {
	store := openTestStore(t)
	m := NewManager(store, 10.0)
	ctx := context.Background()

	session, err := m.GetOrCreateSession(ctx, "sess-1", "1.2.3.4", "free")
	if err != nil {
		t.Fatalf("create session: %v", err)
	}
	if session.SessionID != "sess-1" {
		t.Fatalf("session_id = %q", session.SessionID)
	}
	if session.MaxCostPerSession != 10.0 {
		t.Fatalf("max_cost = %g, want 10", session.MaxCostPerSession)
	}

	again, err := m.GetOrCreateSession(ctx, "sess-1", "", "")
	if err != nil {
		t.Fatalf("get existing: %v", err)
	}
	if again.SessionID != "sess-1" {
		t.Fatalf("second call session_id = %q", again.SessionID)
	}
}

func TestRequireBudgetSucceeds(t *testing.T) {
	store := openTestStore(t)
	m := NewManager(store, 10.0)
	ctx := context.Background()

	_, _ = m.GetOrCreateSession(ctx, "sess-2", "", "free")
	session, err := m.RequireBudget(ctx, "sess-2", 5.0)
	if err != nil {
		t.Fatalf("require budget: %v", err)
	}
	if session.CurrentCost < 5.0 {
		t.Fatalf("current_cost = %g, want >= 5", session.CurrentCost)
	}
}

func TestRequireBudgetExceeded(t *testing.T) {
	store := openTestStore(t)
	m := NewManager(store, 1.0)
	ctx := context.Background()

	_, _ = m.GetOrCreateSession(ctx, "sess-3", "", "free")
	_, err := m.RequireBudget(ctx, "sess-3", 5.0)
	if err == nil {
		t.Fatal("expected budget exceeded error")
	}
	if got := err.Error(); !contains(got, "budget exceeded") {
		t.Fatalf("error = %q", got)
	}
}

func TestSettleCostAdjustsReservation(t *testing.T) {
	store := openTestStore(t)
	m := NewManager(store, 25.0)
	ctx := context.Background()

	_, _ = m.GetOrCreateSession(ctx, "sess-4", "", "free")
	_, err := m.RequireBudget(ctx, "sess-4", 5.0)
	if err != nil {
		t.Fatalf("reserve: %v", err)
	}
	if err := m.SettleCost(ctx, "sess-4", 5.0, 1.0); err != nil {
		t.Fatalf("settle: %v", err)
	}
	session, err := store.GetSessionRequired(ctx, "sess-4")
	if err != nil {
		t.Fatalf("get session: %v", err)
	}
	if session.CurrentCost < 0.9 || session.CurrentCost > 1.1 {
		t.Fatalf("current_cost = %g, want ~1.0", session.CurrentCost)
	}
}

func TestAddCost(t *testing.T) {
	store := openTestStore(t)
	m := NewManager(store, 25.0)
	ctx := context.Background()

	_, _ = m.GetOrCreateSession(ctx, "sess-5", "", "free")
	if err := m.AddCost(ctx, "sess-5", 2.5); err != nil {
		t.Fatalf("add cost: %v", err)
	}
	session, err := store.GetSessionRequired(ctx, "sess-5")
	if err != nil {
		t.Fatalf("get session: %v", err)
	}
	if session.CurrentCost != 2.5 {
		t.Fatalf("current_cost = %g, want 2.5", session.CurrentCost)
	}
}

func TestResetSession(t *testing.T) {
	store := openTestStore(t)
	m := NewManager(store, 10.0)
	ctx := context.Background()

	_, _ = m.GetOrCreateSession(ctx, "sess-6", "", "free")
	_ = m.AddCost(ctx, "sess-6", 5.0)
	if err := m.ResetSession(ctx, "sess-6", 20.0); err != nil {
		t.Fatalf("reset: %v", err)
	}
	session, err := store.GetSessionRequired(ctx, "sess-6")
	if err != nil {
		t.Fatalf("get session: %v", err)
	}
	if session.CurrentCost != 0 {
		t.Fatalf("current_cost = %g, want 0", session.CurrentCost)
	}
	if session.MaxCostPerSession != 20.0 {
		t.Fatalf("max_cost = %g, want 20", session.MaxCostPerSession)
	}
}

func TestSetMaxCostPerSession(t *testing.T) {
	store := openTestStore(t)
	m := NewManager(store, 10.0)

	m.SetMaxCostPerSession(50.0)
	ctx := context.Background()
	session, err := m.GetOrCreateSession(ctx, "sess-7", "", "free")
	if err != nil {
		t.Fatalf("create: %v", err)
	}
	if session.MaxCostPerSession != 50.0 {
		t.Fatalf("max_cost = %g, want 50", session.MaxCostPerSession)
	}

	m.SetMaxCostPerSession(-1)
	session2, _ := m.GetOrCreateSession(ctx, "sess-8", "", "free")
	if session2.MaxCostPerSession != 50.0 {
		t.Fatalf("negative max_cost should be ignored, got %g", session2.MaxCostPerSession)
	}
}

func TestCheckBudget(t *testing.T) {
	store := openTestStore(t)
	m := NewManager(store, 10.0)
	ctx := context.Background()

	_, _ = m.GetOrCreateSession(ctx, "sess-9", "", "free")

	ok, _, err := m.CheckBudget(ctx, "sess-9", 5.0)
	if err != nil {
		t.Fatalf("check: %v", err)
	}
	if !ok {
		t.Fatal("expected budget to be sufficient")
	}

	ok, _, err = m.CheckBudget(ctx, "sess-9", 15.0)
	if err != nil {
		t.Fatalf("check: %v", err)
	}
	if ok {
		t.Fatal("expected budget to be exceeded")
	}
}

func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || len(s) > 0 && containsHelper(s, substr))
}

func containsHelper(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}
