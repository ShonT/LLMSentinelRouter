package judge

import (
	"testing"
	"time"
)

func TestHealthTrackerOpensCircuitAfterThreshold(t *testing.T) {
	h := NewHealthTracker(2, 30)
	h.RecordFailure("judge-a")
	if !h.IsAvailable("judge-a") {
		t.Fatal("circuit should stay closed after one failure")
	}
	h.RecordFailure("judge-a")
	if h.IsAvailable("judge-a") {
		t.Fatal("circuit should open after threshold failures")
	}
	h.RecordSuccess("judge-a")
	if !h.IsAvailable("judge-a") {
		t.Fatal("circuit should close after success")
	}
}

func TestHealthTrackerCooldownExpires(t *testing.T) {
	h := NewHealthTracker(1, 1)
	h.RecordFailure("judge-b")
	if h.IsAvailable("judge-b") {
		t.Fatal("circuit should be open")
	}
	time.Sleep(1100 * time.Millisecond)
	if !h.IsAvailable("judge-b") {
		t.Fatal("circuit should allow retry after cooldown")
	}
}
