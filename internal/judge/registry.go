package judge

import (
	"context"
	"fmt"

	"github.com/ShonT/LLMSentinelRouter/internal/config"
)

// Registry selects judge models with circuit-breaker failover (Python judge_registry parity).
type Registry struct {
	factory     ClientFactory
	health      *HealthTracker
	maxAttempts int
}

func NewRegistry(cfg *config.SentinelConfig, factory ClientFactory, health *HealthTracker, maxAttempts int) *Registry {
	if maxAttempts <= 0 {
		maxAttempts = 3
	}
	return &Registry{factory: factory, health: health, maxAttempts: maxAttempts}
}

func (r *Registry) Evaluate(ctx context.Context, cfg *config.SentinelConfig, prompt string) Result {
	if cfg == nil || !cfg.Judge.Enabled {
		out := heuristic(prompt)
		out.JudgeID = "heuristic"
		return out
	}
	attempts := 0
	for _, modelID := range cfg.Judge.ModelOrder {
		if attempts >= r.maxAttempts {
			break
		}
		if !r.health.IsAvailable(modelID) {
			continue
		}
		model, ok := cfg.Models[modelID]
		if !ok || !model.Enabled {
			continue
		}
		apiKey, ok := firstKey(cfg, model)
		if !ok || apiKey == "" {
			continue
		}
		attempts++
		client := r.factory.NewClient(model.Provider, apiKey, model)
		result, err := callJudge(ctx, client, prompt)
		_ = client.Close()
		if err == nil {
			r.health.RecordSuccess(modelID)
			result.JudgeID = modelID
			return result
		}
		r.health.RecordFailure(modelID)
	}
	out := heuristic(prompt)
	out.JudgeID = "heuristic"
	out.Reasoning = fmt.Sprintf("Judge unavailable after %d attempt(s), using heuristic fallback.", attempts)
	return out
}

func (r *Registry) RegistryStatus(cfg *config.SentinelConfig) []map[string]any {
	if cfg == nil {
		return nil
	}
	out := make([]map[string]any, 0, len(cfg.Judge.ModelOrder))
	for _, modelID := range cfg.Judge.ModelOrder {
		status := r.health.Status(modelID)
		if model, ok := cfg.Models[modelID]; ok {
			status["enabled"] = model.Enabled
			status["provider"] = string(model.Provider)
		}
		out = append(out, status)
	}
	return out
}
