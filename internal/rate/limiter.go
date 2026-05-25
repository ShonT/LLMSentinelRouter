package rate

import (
	"fmt"
	"sync"
	"time"
)

type Window struct {
	mu            sync.Mutex
	requestMinute []event
	requestDay    []event
}

type event struct {
	at     time.Time
	tokens int
}

type Usage struct {
	RequestsLastMinute int `json:"requests_last_minute"`
	TokensLastMinute   int `json:"tokens_last_minute"`
	RequestsLastDay    int `json:"requests_last_day"`
	TokensLastDay      int `json:"tokens_last_day"`
}

type Limiter struct {
	mu           sync.Mutex
	safetyMargin float64
	windows      map[string]*Window
}

func New(safetyMargin float64) *Limiter {
	if safetyMargin <= 0 {
		safetyMargin = 0.95
	}
	return &Limiter{safetyMargin: safetyMargin, windows: map[string]*Window{}}
}

func (l *Limiter) Record(modelID string, tokens int) {
	window := l.window(modelID)
	window.mu.Lock()
	defer window.mu.Unlock()
	now := time.Now().UTC()
	window.requestMinute = append(window.requestMinute, event{at: now, tokens: tokens})
	window.requestDay = append(window.requestDay, event{at: now, tokens: tokens})
	window.cleanup(now)
}

func (l *Limiter) Check(modelID string, rpm, tpm, rpd, tpd, estimatedTokens int) (bool, string, Usage) {
	window := l.window(modelID)
	window.mu.Lock()
	defer window.mu.Unlock()
	now := time.Now().UTC()
	window.cleanup(now)
	usage := window.usage()
	if rpm > 0 && usage.RequestsLastMinute >= int(float64(rpm)*l.safetyMargin) {
		return false, fmt.Sprintf("RPM limit: %d/%d", usage.RequestsLastMinute, rpm), usage
	}
	if tpm > 0 && usage.TokensLastMinute >= int(float64(tpm)*l.safetyMargin) {
		return false, fmt.Sprintf("TPM limit: %d/%d", usage.TokensLastMinute, tpm), usage
	}
	if rpd > 0 && usage.RequestsLastDay >= int(float64(rpd)*l.safetyMargin) {
		return false, fmt.Sprintf("RPD limit: %d/%d", usage.RequestsLastDay, rpd), usage
	}
	if tpd > 0 && usage.TokensLastDay >= int(float64(tpd)*l.safetyMargin) {
		return false, fmt.Sprintf("TPD limit: %d/%d", usage.TokensLastDay, tpd), usage
	}
	if tpm > 0 && estimatedTokens > 0 && usage.TokensLastMinute+estimatedTokens >= int(float64(tpm)*l.safetyMargin) {
		return false, fmt.Sprintf("Projected TPM: %d/%d", usage.TokensLastMinute+estimatedTokens, tpm), usage
	}
	return true, "", usage
}

func (l *Limiter) Usage(modelID string) Usage {
	window := l.window(modelID)
	window.mu.Lock()
	defer window.mu.Unlock()
	window.cleanup(time.Now().UTC())
	return window.usage()
}

func (l *Limiter) window(modelID string) *Window {
	l.mu.Lock()
	defer l.mu.Unlock()
	window := l.windows[modelID]
	if window == nil {
		window = &Window{}
		l.windows[modelID] = window
	}
	return window
}

func (w *Window) cleanup(now time.Time) {
	minuteCutoff := now.Add(-time.Minute)
	dayCutoff := now.Add(-24 * time.Hour)
	w.requestMinute = trimEvents(w.requestMinute, minuteCutoff)
	w.requestDay = trimEvents(w.requestDay, dayCutoff)
}

func (w *Window) usage() Usage {
	usage := Usage{RequestsLastMinute: len(w.requestMinute), RequestsLastDay: len(w.requestDay)}
	for _, ev := range w.requestMinute {
		usage.TokensLastMinute += ev.tokens
	}
	for _, ev := range w.requestDay {
		usage.TokensLastDay += ev.tokens
	}
	return usage
}

func trimEvents(events []event, cutoff time.Time) []event {
	i := 0
	for i < len(events) && events[i].at.Before(cutoff) {
		i++
	}
	if i == 0 {
		return events
	}
	out := events[i:]
	return append(events[:0], out...)
}
