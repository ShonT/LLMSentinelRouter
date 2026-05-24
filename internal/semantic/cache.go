package semantic

import (
	"sync"
	"time"
)

type Stats struct {
	SemanticHash     string
	TotalCalls       int
	WeakCalls        int
	StrongCalls      int
	JudgeInvocations int
	TotalLatencyMS   float64
	TotalCost        float64
	TotalTokens      int
	LastModel        string
	LastCalledAt     time.Time
	FirstSeenAt      time.Time
}

type Cache struct {
	mu                  sync.Mutex
	minSamples          int
	confidenceThreshold float64
	ttl                 time.Duration
	stats               map[string]*Stats
}

func NewCache(minSamples int, confidenceThreshold float64, ttlSeconds int) *Cache {
	if minSamples <= 0 {
		minSamples = 3
	}
	if confidenceThreshold <= 0 {
		confidenceThreshold = 0.75
	}
	if ttlSeconds <= 0 {
		ttlSeconds = 604800
	}
	return &Cache{
		minSamples:          minSamples,
		confidenceThreshold: confidenceThreshold,
		ttl:                 time.Duration(ttlSeconds) * time.Second,
		stats:               map[string]*Stats{},
	}
}

func (c *Cache) Lookup(prompt string, context any) (*Stats, bool) {
	hash := HashPayload(prompt, context)
	c.mu.Lock()
	defer c.mu.Unlock()
	stats, ok := c.stats[hash]
	if !ok {
		return nil, false
	}
	if time.Since(stats.LastCalledAt) > c.ttl {
		delete(c.stats, hash)
		return nil, false
	}
	cp := *stats
	return &cp, true
}

func (c *Cache) Confidence(hash string) float64 {
	c.mu.Lock()
	defer c.mu.Unlock()
	stats, ok := c.stats[hash]
	if !ok {
		return 0
	}
	return confidence(stats)
}

func (c *Cache) ConfidentRoute(prompt string, context any) (route string, confidenceValue float64, ok bool) {
	stats, found := c.Lookup(prompt, context)
	if !found {
		return "", 0, false
	}
	conf := confidence(stats)
	if stats.TotalCalls < c.minSamples || conf < c.confidenceThreshold {
		return "", conf, false
	}
	if stats.WeakCalls > stats.StrongCalls {
		return "weak", conf, true
	}
	if stats.StrongCalls > stats.WeakCalls {
		return "strong", conf, true
	}
	return "", conf, false
}

func (c *Cache) Record(prompt string, context any, modelUsed, route string, latencyMS float64, judgeInvoked bool, cost float64, tokens int) {
	hash := HashPayload(prompt, context)
	now := time.Now().UTC()
	c.mu.Lock()
	defer c.mu.Unlock()
	stats, ok := c.stats[hash]
	if !ok {
		stats = &Stats{SemanticHash: hash, FirstSeenAt: now}
		c.stats[hash] = stats
	}
	stats.TotalCalls++
	switch route {
	case "strong":
		stats.StrongCalls++
	default:
		stats.WeakCalls++
	}
	if judgeInvoked {
		stats.JudgeInvocations++
	}
	stats.TotalLatencyMS += latencyMS
	stats.TotalCost += cost
	stats.TotalTokens += tokens
	stats.LastModel = modelUsed
	stats.LastCalledAt = now
}

func (c *Cache) Reset() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.stats = map[string]*Stats{}
}

func confidence(stats *Stats) float64 {
	routable := stats.WeakCalls + stats.StrongCalls
	if routable == 0 {
		return 0
	}
	maxCalls := stats.WeakCalls
	if stats.StrongCalls > maxCalls {
		maxCalls = stats.StrongCalls
	}
	return float64(maxCalls) / float64(routable)
}
