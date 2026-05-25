package rate

import "testing"

func TestLimiterEnforcesRPMAndProjectedTPM(t *testing.T) {
	limiter := New(1.0)
	limiter.Record("m1", 10)
	allowed, reason, usage := limiter.Check("m1", 1, 0, 0, 0, 0)
	if allowed {
		t.Fatal("expected RPM limit")
	}
	if reason == "" || usage.RequestsLastMinute != 1 {
		t.Fatalf("unexpected reason=%q usage=%+v", reason, usage)
	}

	allowed, reason, _ = limiter.Check("m2", 0, 20, 0, 0, 25)
	if allowed {
		t.Fatal("expected projected TPM limit")
	}
	if reason == "" {
		t.Fatal("expected reason")
	}
}
