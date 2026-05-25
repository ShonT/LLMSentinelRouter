package cycle

import (
	"testing"
)

func TestDetectPromptReturnsFalseForUniquePrompts(t *testing.T) {
	d := NewDetector("sess-1", 3, 50)
	if d.DetectPrompt("hello world") {
		t.Fatal("should not detect cycle on first prompt")
	}
	d.Add("hello world", "response one")
	if d.DetectPrompt("completely different topic about science") {
		t.Fatal("should not detect cycle for different prompt")
	}
}

func TestDetectPromptReturnsTrueForRepeatedPrompts(t *testing.T) {
	d := NewDetector("sess-1", 3, 50)
	prompt := "explain quantum computing in simple terms"
	d.Add(prompt, "quantum computing uses qubits")

	if !d.DetectPrompt(prompt) {
		t.Fatal("should detect cycle for identical prompt")
	}
}

func TestDetectPromptReturnsTrueForNearlyIdenticalPrompts(t *testing.T) {
	d := NewDetector("sess-1", 10, 50)
	prompt := "explain quantum computing in simple terms please"
	d.Add(prompt, "quantum computing uses qubits")

	if !d.DetectPrompt("explain quantum computing in simple terms please") {
		t.Fatal("should detect cycle for nearly identical prompt")
	}
}

func TestClearLastResponseAffectsDetection(t *testing.T) {
	d := NewDetector("sess-1", 3, 50)
	d.Add("hello", "world")
	d.ClearLastResponse()

	if d.DetectPrompt("something entirely new and different from before") {
		t.Fatal("should not detect cycle after clear with new prompt")
	}
}

func TestDetectorMaxHashesEviction(t *testing.T) {
	d := NewDetector("sess-1", 0, 5)
	for i := 0; i < 10; i++ {
		d.Add("prompt-"+string(rune('a'+i)), "response-"+string(rune('a'+i)))
	}
	if len(d.recentHashes) > 5 {
		t.Fatalf("hashes = %d, want <= 5", len(d.recentHashes))
	}
}

func TestRegistryGetCreatesAndCaches(t *testing.T) {
	r := NewRegistry(5, 3, 50)
	d1 := r.Get("sess-1")
	d2 := r.Get("sess-1")
	if d1 != d2 {
		t.Fatal("same session should return same detector")
	}
	d3 := r.Get("sess-2")
	if d1 == d3 {
		t.Fatal("different sessions should return different detectors")
	}
}

func TestRegistryLRUEviction(t *testing.T) {
	r := NewRegistry(3, 3, 50)

	r.Get("sess-1")
	r.Get("sess-2")
	r.Get("sess-3")
	r.Get("sess-4")

	if len(r.detectors) > 3 {
		t.Fatalf("detectors = %d, want <= 3", len(r.detectors))
	}
	if _, ok := r.detectors["sess-1"]; ok {
		t.Fatal("oldest session should have been evicted")
	}
	if _, ok := r.detectors["sess-4"]; !ok {
		t.Fatal("newest session should be present")
	}
}

func TestRegistryTouchReordersLRU(t *testing.T) {
	r := NewRegistry(3, 3, 50)

	r.Get("sess-1")
	r.Get("sess-2")
	r.Get("sess-3")

	r.Get("sess-1")
	r.Get("sess-4")

	if _, ok := r.detectors["sess-1"]; !ok {
		t.Fatal("touched session should not have been evicted")
	}
	if _, ok := r.detectors["sess-2"]; ok {
		t.Fatal("untouched oldest session should have been evicted")
	}
}
