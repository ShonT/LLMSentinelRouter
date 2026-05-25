package cycle

import (
	"sync"

	"github.com/ShonT/LLMSentinelRouter/internal/semantic"
)

type Detector struct {
	sessionID    string
	threshold    int
	maxHashes    int
	recentHashes []uint64
	lastResponse string
}

func NewDetector(sessionID string, threshold, maxHashes int) *Detector {
	if threshold <= 0 {
		threshold = 3
	}
	if maxHashes <= 0 {
		maxHashes = 50
	}
	return &Detector{sessionID: sessionID, threshold: threshold, maxHashes: maxHashes}
}

func (d *Detector) DetectPrompt(prompt string) bool {
	current := semantic.SimHash(prompt + "\n" + d.lastResponse)
	for _, previous := range d.recentHashes {
		if semantic.HammingDistance(current, previous) <= d.threshold {
			return true
		}
	}
	return false
}

func (d *Detector) Add(prompt, response string) {
	hash := semantic.SimHash(prompt + "\n" + response)
	d.recentHashes = append(d.recentHashes, hash)
	if len(d.recentHashes) > d.maxHashes {
		copy(d.recentHashes, d.recentHashes[len(d.recentHashes)-d.maxHashes:])
		d.recentHashes = d.recentHashes[:d.maxHashes]
	}
	d.lastResponse = response
}

func (d *Detector) ClearLastResponse() {
	d.lastResponse = ""
}

type Registry struct {
	mu        sync.Mutex
	maxSize   int
	threshold int
	maxHashes int
	detectors map[string]*Detector
	order     []string
}

func NewRegistry(maxSize, threshold, maxHashes int) *Registry {
	if maxSize <= 0 {
		maxSize = 1000
	}
	if threshold <= 0 {
		threshold = 3
	}
	if maxHashes <= 0 {
		maxHashes = 50
	}
	return &Registry{maxSize: maxSize, threshold: threshold, maxHashes: maxHashes, detectors: map[string]*Detector{}}
}

func (r *Registry) Get(sessionID string) *Detector {
	r.mu.Lock()
	defer r.mu.Unlock()
	if detector, ok := r.detectors[sessionID]; ok {
		r.touch(sessionID)
		return detector
	}
	for len(r.order) >= r.maxSize {
		oldest := r.order[0]
		r.order = r.order[1:]
		delete(r.detectors, oldest)
	}
	detector := NewDetector(sessionID, r.threshold, r.maxHashes)
	r.detectors[sessionID] = detector
	r.order = append(r.order, sessionID)
	return detector
}

func (r *Registry) touch(sessionID string) {
	for i, item := range r.order {
		if item == sessionID {
			copy(r.order[i:], r.order[i+1:])
			r.order[len(r.order)-1] = sessionID
			return
		}
	}
}
