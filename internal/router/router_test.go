package router

import (
	"testing"

	"github.com/ShonT/LLMSentinelRouter/internal/provider"
)

func TestDecideRouteWeakBelowThreshold(t *testing.T) {
	route := decideRoute(0.3, "LOW", 0.7, false, false)
	if route != "weak" {
		t.Fatalf("route = %q, want weak", route)
	}
}

func TestDecideRouteStrongAboveThreshold(t *testing.T) {
	route := decideRoute(0.9, "HIGH", 0.7, false, false)
	if route != "strong" {
		t.Fatalf("route = %q, want strong", route)
	}
}

func TestDecideRouteCycleDetectedForcesStrong(t *testing.T) {
	route := decideRoute(0.1, "LOW", 0.7, false, true)
	if route != "strong" {
		t.Fatalf("route = %q, want strong on cycle", route)
	}
}

func TestDecideRouteStrictModeDowngrades(t *testing.T) {
	route := decideRoute(0.8, "LOW", 0.7, true, false)
	if route != "weak" {
		t.Fatalf("route = %q, want weak (strict mode downgrade, score-0.15 < threshold)", route)
	}
}

func TestDecideRouteStrictModeHighImpactStaysStrong(t *testing.T) {
	route := decideRoute(0.95, "HIGH", 0.7, true, false)
	if route != "strong" {
		t.Fatalf("route = %q, want strong (HIGH impact in strict mode)", route)
	}
}

func TestDecideRouteStrictModeNotHighDowngrades(t *testing.T) {
	route := decideRoute(0.95, "MEDIUM", 0.7, true, false)
	if route != "weak" {
		t.Fatalf("route = %q, want weak (MEDIUM impact in strict mode)", route)
	}
}

func TestBuildReasonCycleDetected(t *testing.T) {
	reason := buildReason("strong", 0.1, "LOW", 0.7, false, true)
	if reason != "Cycle detected - forced strong model." {
		t.Fatalf("reason = %q", reason)
	}
}

func TestBuildReasonAboveThreshold(t *testing.T) {
	reason := buildReason("strong", 0.9, "HIGH", 0.7, false, false)
	if reason == "" {
		t.Fatal("reason should not be empty")
	}
}

func TestBuildReasonBelowThreshold(t *testing.T) {
	reason := buildReason("weak", 0.3, "LOW", 0.7, false, false)
	if reason == "" {
		t.Fatal("reason should not be empty")
	}
}

func TestBuildReasonStrictModeDowngrade(t *testing.T) {
	reason := buildReason("weak", 0.8, "MEDIUM", 0.7, true, false)
	if reason == "" {
		t.Fatal("reason should not be empty")
	}
}

func TestNewIDUniqueness(t *testing.T) {
	seen := map[string]bool{}
	for i := 0; i < 100; i++ {
		id := NewID()
		if seen[id] {
			t.Fatalf("duplicate ID: %s", id)
		}
		seen[id] = true
	}
}

func TestNewIDFormat(t *testing.T) {
	id := NewID()
	if len(id) == 0 {
		t.Fatal("empty ID")
	}
	parts := 0
	for _, c := range id {
		if c == '-' {
			parts++
		}
	}
	if parts != 4 {
		t.Fatalf("ID %q should have 4 dashes (UUID v4 format)", id)
	}
}

func TestFinalCostProviderReported(t *testing.T) {
	cost, source, computed := finalCost(provider.Response{Cost: 0.05})
	if cost != 0.05 {
		t.Fatalf("cost = %g, want 0.05", cost)
	}
	if source != "provider" {
		t.Fatalf("source = %q, want provider", source)
	}
	if computed != nil {
		t.Fatalf("computed should be nil for provider cost")
	}
}

func TestFinalCostNegativeFallsBackToComputed(t *testing.T) {
	cost, source, computed := finalCost(provider.Response{Cost: -1})
	if cost != 0 {
		t.Fatalf("cost = %g, want 0", cost)
	}
	if source != "computed" {
		t.Fatalf("source = %q, want computed", source)
	}
	if computed == nil {
		t.Fatal("computed should be non-nil")
	}
}

func TestNullableString(t *testing.T) {
	ns := nullableString("hello")
	if !ns.Valid || ns.String != "hello" {
		t.Fatalf("ns = %+v", ns)
	}
	empty := nullableString("")
	if empty.Valid {
		t.Fatal("empty string should be invalid")
	}
}

func TestNullableFloat(t *testing.T) {
	val := 3.14
	nf := nullableFloat(&val)
	if !nf.Valid || nf.Float64 != 3.14 {
		t.Fatalf("nf = %+v", nf)
	}
	nilFloat := nullableFloat(nil)
	if nilFloat.Valid {
		t.Fatal("nil should be invalid")
	}
}

func TestTruncate(t *testing.T) {
	short := truncate("hello", 10)
	if short != "hello" {
		t.Fatalf("short = %q", short)
	}
	long := truncate("hello world", 5)
	if long != "hello" {
		t.Fatalf("long = %q", long)
	}
}

func TestShortHash(t *testing.T) {
	h1 := shortHash("hello")
	h2 := shortHash("hello")
	h3 := shortHash("world")
	if h1 != h2 {
		t.Fatal("same input should produce same hash")
	}
	if h1 == h3 {
		t.Fatal("different inputs should produce different hashes")
	}
	if len(h1) != 8 {
		t.Fatalf("hash len = %d, want 8", len(h1))
	}
}
