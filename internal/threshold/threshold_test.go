package threshold

import "testing"

func TestDynamicThresholdAdjustmentAndStrictMode(t *testing.T) {
	d := New(0.05, 3, 0.70)
	d.AddDecision(true)
	d.AddDecision(true)
	if d.IsStrictMode() {
		t.Fatal("strict mode before full window = true")
	}
	d.AddDecision(false)
	if !d.IsStrictMode() {
		t.Fatal("strict mode after high escalation window = false")
	}
	next, changed := d.Adjust()
	if !changed {
		t.Fatal("expected threshold adjustment")
	}
	if next < 0.709 || next > 0.711 {
		t.Fatalf("threshold = %v, want 0.71", next)
	}
}
