package judge

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"regexp"
	"strings"
	"time"

	"github.com/ShonT/LLMSentinelRouter/internal/config"
	"github.com/ShonT/LLMSentinelRouter/internal/provider"
)

type Result struct {
	ComplexityScore float64
	ImpactScope     string
	Reasoning       string
	JudgeID         string
	LatencyMS       float64
}

type ClientFactory interface {
	NewClient(providerType config.ProviderType, apiKey string, model config.ModelDefinition) provider.Client
}

type Judge struct {
	config  *config.SentinelConfig
	factory ClientFactory
}

func New(cfg *config.SentinelConfig, factory ClientFactory) *Judge {
	return &Judge{config: cfg, factory: factory}
}

func (j *Judge) Evaluate(ctx context.Context, prompt string) Result {
	start := time.Now()
	if j.config == nil || !j.config.Judge.Enabled {
		result := heuristic(prompt)
		result.LatencyMS = float64(time.Since(start).Milliseconds())
		return result
	}
	for _, modelID := range j.config.Judge.ModelOrder {
		model, ok := j.config.Models[modelID]
		if !ok || !model.Enabled {
			continue
		}
		apiKey, ok := firstKey(j.config, model)
		if !ok || apiKey == "" {
			continue
		}
		client := j.factory.NewClient(model.Provider, apiKey, model)
		result, err := callJudge(ctx, client, prompt)
		_ = client.Close()
		if err == nil {
			result.JudgeID = modelID
			result.LatencyMS = float64(time.Since(start).Milliseconds())
			return result
		}
	}
	result := heuristic(prompt)
	result.Reasoning = "Judge unavailable, using heuristic fallback."
	result.LatencyMS = float64(time.Since(start).Milliseconds())
	return result
}

func ComplexityToRoute(score, threshold float64) string {
	if score >= threshold {
		return "strong"
	}
	return "weak"
}

func callJudge(ctx context.Context, client provider.Client, prompt string) (Result, error) {
	system := "You are a stingy routing judge. Return only JSON with complexity_score between 0 and 1, impact_scope LOW/MEDIUM/HIGH, and reasoning."
	user := fmt.Sprintf("Classify this prompt for LLM routing:\n\n%s", prompt)
	temp := 0.1
	resp, err := client.ChatCompletion(ctx, []provider.Message{
		{Role: "system", Content: system},
		{Role: "user", Content: user},
	}, provider.Options{Temperature: &temp})
	if err != nil {
		return Result{}, err
	}
	return parse(resp.Content)
}

func parse(content string) (Result, error) {
	content = strings.TrimSpace(content)
	content = strings.Trim(content, "`")
	start := strings.Index(content, "{")
	end := strings.LastIndex(content, "}")
	if start >= 0 && end > start {
		content = content[start : end+1]
	}
	var raw struct {
		ComplexityScore float64 `json:"complexity_score"`
		ImpactScope     string  `json:"impact_scope"`
		Reasoning       string  `json:"reasoning"`
	}
	if err := json.Unmarshal([]byte(content), &raw); err != nil {
		return Result{}, err
	}
	scope := strings.ToUpper(raw.ImpactScope)
	if scope != "LOW" && scope != "MEDIUM" && scope != "HIGH" {
		scope = "LOW"
	}
	score := math.Max(0, math.Min(1, raw.ComplexityScore))
	if raw.Reasoning == "" {
		raw.Reasoning = "No reasoning supplied."
	}
	return Result{ComplexityScore: score, ImpactScope: scope, Reasoning: raw.Reasoning}, nil
}

func heuristic(prompt string) Result {
	lower := strings.ToLower(prompt)
	wordCount := len(strings.Fields(prompt))
	score := 0.1
	scope := "LOW"
	reason := "Simple prompt by heuristic."
	complexTerms := []string{"architecture", "debug", "security", "migration", "database", "distributed", "optimize", "production", "refactor", "analyze"}
	for _, term := range complexTerms {
		if strings.Contains(lower, term) {
			score += 0.12
		}
	}
	if wordCount > 50 {
		score += 0.25
	}
	if wordCount > 150 {
		score += 0.25
	}
	if regexp.MustCompile(`(?i)\b(delete|deploy|prod|credentials|payment|legal|medical)\b`).MatchString(prompt) {
		score += 0.2
		scope = "HIGH"
		reason = "High-impact keyword detected."
	}
	if score >= 0.7 && scope != "HIGH" {
		scope = "MEDIUM"
		reason = "Complex prompt by heuristic."
	}
	if score > 1 {
		score = 1
	}
	return Result{ComplexityScore: score, ImpactScope: scope, Reasoning: reason}
}

func firstKey(cfg *config.SentinelConfig, model config.ModelDefinition) (string, bool) {
	instances := model.KeyInstances
	if len(instances) == 0 && model.KeyInstance != "" {
		instances = []string{model.KeyInstance}
	}
	for _, instanceID := range instances {
		inst, ok := cfg.KeyInstances[instanceID]
		if !ok || !inst.Enabled {
			continue
		}
		key, ok := cfg.Keys[inst.KeyRef]
		if ok && key.Value != "" {
			return key.Value, true
		}
	}
	return "", false
}
