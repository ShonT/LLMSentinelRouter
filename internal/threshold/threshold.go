package threshold

import "sync"

type Dynamic struct {
	mu         sync.Mutex
	targetRate float64
	windowSize int
	threshold  float64
	window     []bool
}

func New(targetRate float64, windowSize int, initialThreshold float64) *Dynamic {
	if targetRate <= 0 {
		targetRate = 0.05
	}
	if windowSize <= 0 {
		windowSize = 20
	}
	if initialThreshold <= 0 {
		initialThreshold = 0.7
	}
	return &Dynamic{targetRate: targetRate, windowSize: windowSize, threshold: initialThreshold}
}

func (d *Dynamic) AddDecision(strong bool) {
	d.mu.Lock()
	defer d.mu.Unlock()
	if len(d.window) == d.windowSize {
		copy(d.window, d.window[1:])
		d.window[len(d.window)-1] = strong
		return
	}
	d.window = append(d.window, strong)
}

func (d *Dynamic) Rate() float64 {
	d.mu.Lock()
	defer d.mu.Unlock()
	return d.rateLocked()
}

func (d *Dynamic) IsStrictMode() bool {
	d.mu.Lock()
	defer d.mu.Unlock()
	return len(d.window) >= d.windowSize && d.rateLocked() > d.targetRate
}

func (d *Dynamic) Threshold() float64 {
	d.mu.Lock()
	defer d.mu.Unlock()
	return d.threshold
}

func (d *Dynamic) Adjust() (float64, bool) {
	d.mu.Lock()
	defer d.mu.Unlock()
	if len(d.window) < d.windowSize {
		return d.threshold, false
	}
	rate := d.rateLocked()
	old := d.threshold
	if rate > d.targetRate {
		d.threshold = minFloat(0.99, d.threshold+0.01)
	} else if rate < d.targetRate-0.02 {
		d.threshold = maxFloat(0.0, d.threshold-0.02)
	}
	return d.threshold, old != d.threshold
}

func (d *Dynamic) Reset(newThreshold *float64) {
	d.mu.Lock()
	defer d.mu.Unlock()
	d.window = nil
	if newThreshold != nil {
		d.threshold = *newThreshold
	}
}

func (d *Dynamic) rateLocked() float64 {
	if len(d.window) == 0 {
		return 0
	}
	strong := 0
	for _, item := range d.window {
		if item {
			strong++
		}
	}
	return float64(strong) / float64(len(d.window))
}

func minFloat(a, b float64) float64 {
	if a < b {
		return a
	}
	return b
}

func maxFloat(a, b float64) float64 {
	if a > b {
		return a
	}
	return b
}
