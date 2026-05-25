package semantic

import (
	"context"
	"database/sql"
	"sync"

	"github.com/ShonT/LLMSentinelRouter/internal/storage"
)

type PersistentCache struct {
	inner  *Cache
	store  *storage.Store
	mu     sync.Mutex
	loaded bool
}

func NewPersistentCache(store *storage.Store, minSamples int, confidenceThreshold float64, ttlSeconds int) *PersistentCache {
	return &PersistentCache{
		inner: NewCache(minSamples, confidenceThreshold, ttlSeconds),
		store: store,
	}
}

func (c *PersistentCache) ensureLoaded(ctx context.Context) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.loaded {
		return nil
	}
	rows, err := c.store.LoadSemanticCacheStats(ctx)
	if err != nil {
		return err
	}
	loaded := make(map[string]Stats, len(rows))
	for _, row := range rows {
		loaded[row.SemanticHash] = Stats{
			SemanticHash:     row.SemanticHash,
			TotalCalls:       row.TotalCalls,
			WeakCalls:        row.WeakCalls,
			StrongCalls:      row.StrongCalls,
			JudgeInvocations: row.JudgeInvocations,
			TotalLatencyMS:   row.TotalLatencyMS,
			TotalCost:        row.TotalCost,
			TotalTokens:      row.TotalTokens,
			LastModel:        nullStringValue(row.LastModel),
			LastCalledAt:     row.LastCalledAt,
			FirstSeenAt:      row.FirstSeenAt,
		}
	}
	c.inner.LoadFromStats(loaded)
	c.loaded = true
	return nil
}

func (c *PersistentCache) Lookup(prompt string, contextData any) (*Stats, bool) {
	_ = c.ensureLoaded(context.Background())
	return c.inner.Lookup(prompt, contextData)
}

func (c *PersistentCache) Confidence(hash string) float64 {
	return c.inner.Confidence(hash)
}

func (c *PersistentCache) ConfidentRoute(prompt string, contextData any) (string, float64, bool) {
	_ = c.ensureLoaded(context.Background())
	return c.inner.ConfidentRoute(prompt, contextData)
}

func (c *PersistentCache) Record(prompt string, contextData any, modelUsed, route string, latencyMS float64, judgeInvoked bool, cost float64, tokens int) {
	_ = c.ensureLoaded(context.Background())
	c.inner.Record(prompt, contextData, modelUsed, route, latencyMS, judgeInvoked, cost, tokens)
	stats, ok := c.inner.Lookup(prompt, contextData)
	if !ok || stats == nil {
		return
	}
	_ = c.store.UpsertSemanticCacheStats(context.Background(), storage.SemanticCacheStats{
		SemanticHash:     stats.SemanticHash,
		TotalCalls:       stats.TotalCalls,
		WeakCalls:        stats.WeakCalls,
		StrongCalls:      stats.StrongCalls,
		JudgeInvocations: stats.JudgeInvocations,
		TotalLatencyMS:   stats.TotalLatencyMS,
		TotalCost:        stats.TotalCost,
		TotalTokens:      stats.TotalTokens,
		LastModel:        sql.NullString{String: stats.LastModel, Valid: stats.LastModel != ""},
		LastCalledAt:     stats.LastCalledAt,
		FirstSeenAt:      stats.FirstSeenAt,
	})
	_ = c.store.InsertSemanticCacheEntry(context.Background(), storage.SemanticCacheEntry{
		SemanticHash:  stats.SemanticHash,
		ContextHash:   HashPayload("", contextData),
		PromptPreview: truncate(prompt, 500),
		LatencyMS:     latencyMS,
		JudgeInvoked:  judgeInvoked,
		ModelUsed:     modelUsed,
		Cost:          cost,
		TotalTokens:   tokens,
	})
}

func (c *PersistentCache) Reset() {
	c.inner.Reset()
	_ = c.store.ClearSemanticCacheStats(context.Background())
	c.mu.Lock()
	c.loaded = true
	c.mu.Unlock()
}

func (c *PersistentCache) Summary(ctx context.Context) (hits, misses, clusters int, err error) {
	_ = c.ensureLoaded(ctx)
	return c.store.SemanticCacheSummary(ctx)
}

func nullStringValue(value sql.NullString) string {
	if value.Valid {
		return value.String
	}
	return ""
}

func truncate(value string, maxLen int) string {
	if len(value) <= maxLen {
		return value
	}
	return value[:maxLen]
}
