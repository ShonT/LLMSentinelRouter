package semantic

import "testing"

func TestSimHashAndCacheRecommendation(t *testing.T) {
	a := SimHash("Explain quantum computing simply")
	b := SimHash("Explain quantum computing simply")
	if HammingDistance(a, b) != 0 {
		t.Fatal("same text should have zero distance")
	}
	cache := NewCache(2, 0.75, 60)
	cache.Record("hello", nil, "m1", "weak", 10, false, 0.1, 10)
	cache.Record("hello", nil, "m1", "weak", 10, false, 0.1, 10)
	route, confidence, ok := cache.ConfidentRoute("hello", nil)
	if !ok || route != "weak" || confidence != 1 {
		t.Fatalf("route=%q confidence=%v ok=%v", route, confidence, ok)
	}
}
