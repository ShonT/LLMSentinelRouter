package judge

import (
	"sync"
	"time"
)

// HealthTracker implements per-judge circuit breaking (failure threshold + cooldown).
type HealthTracker struct {
	mu                sync.RWMutex
	failureThreshold  int
	cooldown          time.Duration
	failures          map[string]int
	circuitOpenUntil  map[string]time.Time
	lastFailure       map[string]time.Time
}

func NewHealthTracker(failureThreshold, cooldownSeconds int) *HealthTracker {
	if failureThreshold <= 0 {
		failureThreshold = 3
	}
	if cooldownSeconds <= 0 {
		cooldownSeconds = 60
	}
	return &HealthTracker{
		failureThreshold: failureThreshold,
		cooldown:         time.Duration(cooldownSeconds) * time.Second,
		failures:         map[string]int{},
		circuitOpenUntil: map[string]time.Time{},
		lastFailure:      map[string]time.Time{},
	}
}

func (h *HealthTracker) IsAvailable(judgeID string) bool {
	h.mu.RLock()
	defer h.mu.RUnlock()
	until, open := h.circuitOpenUntil[judgeID]
	if !open {
		return true
	}
	return time.Now().After(until)
}

func (h *HealthTracker) RecordSuccess(judgeID string) {
	h.mu.Lock()
	defer h.mu.Unlock()
	delete(h.failures, judgeID)
	delete(h.circuitOpenUntil, judgeID)
	delete(h.lastFailure, judgeID)
}

func (h *HealthTracker) RecordFailure(judgeID string) {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.failures[judgeID]++
	h.lastFailure[judgeID] = time.Now()
	if h.failures[judgeID] >= h.failureThreshold {
		h.circuitOpenUntil[judgeID] = time.Now().Add(h.cooldown)
	}
}

func (h *HealthTracker) Status(judgeID string) map[string]any {
	h.mu.RLock()
	defer h.mu.RUnlock()
	openUntil, circuitOpen := h.circuitOpenUntil[judgeID]
	status := map[string]any{
		"judge_id":          judgeID,
		"failures":          h.failures[judgeID],
		"circuit_open":      circuitOpen && time.Now().Before(openUntil),
		"failure_threshold": h.failureThreshold,
		"cooldown_seconds":  int(h.cooldown / time.Second),
	}
	if circuitOpen {
		status["circuit_open_until"] = openUntil.UTC().Format(time.RFC3339)
	}
	if t, ok := h.lastFailure[judgeID]; ok {
		status["last_failure"] = t.UTC().Format(time.RFC3339)
	}
	return status
}
