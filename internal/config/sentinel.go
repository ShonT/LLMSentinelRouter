package config

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"regexp"
	"sort"
	"strings"
)

type ProviderType string

const (
	ProviderGroq       ProviderType = "groq"
	ProviderOpenRouter ProviderType = "openrouter"
	ProviderDeepSeek   ProviderType = "deepseek"
	ProviderAnthropic  ProviderType = "anthropic"
	ProviderGemini     ProviderType = "gemini"
)

type Key struct {
	Type  ProviderType `json:"type"`
	Value string       `json:"value"`
}

type KeyInstance struct {
	KeyRef      string `json:"key_ref"`
	Priority    int    `json:"priority"`
	Enabled     bool   `json:"enabled"`
	Description string `json:"description,omitempty"`
}

func (k *KeyInstance) UnmarshalJSON(data []byte) error {
	type alias KeyInstance
	var raw alias
	raw.Enabled = true
	if err := json.Unmarshal(data, &raw); err != nil {
		return err
	}
	*k = KeyInstance(raw)
	return nil
}

type Pricing struct {
	InputCostPerM  float64 `json:"input_cost_per_m"`
	OutputCostPerM float64 `json:"output_cost_per_m"`
}

type Limits struct {
	RequestsPerMinute int `json:"requests_per_minute"`
	RequestsPerDay    int `json:"requests_per_day"`
	TokensPerMinute   int `json:"tokens_per_minute"`
	TokensPerDay      int `json:"tokens_per_day,omitempty"`
}

type ModelDefinition struct {
	Enabled      bool         `json:"enabled"`
	Provider     ProviderType `json:"provider"`
	ModelID      string       `json:"model_id"`
	KeyInstance  string       `json:"key_instance,omitempty"`
	KeyInstances []string     `json:"key_instances,omitempty"`
	Pricing      Pricing      `json:"pricing"`
	Limits       Limits       `json:"limits"`
	DisplayName  string       `json:"display_name,omitempty"`
}

func (m *ModelDefinition) UnmarshalJSON(data []byte) error {
	type alias ModelDefinition
	var raw alias
	raw.Enabled = true
	if err := json.Unmarshal(data, &raw); err != nil {
		return err
	}
	*m = ModelDefinition(raw)
	return nil
}

type RoutingTier struct {
	Order []string `json:"order"`
}

type RoutingPolicy struct {
	WeakTier   RoutingTier `json:"weak_tier"`
	StrongTier RoutingTier `json:"strong_tier"`
}

type JudgeConfig struct {
	Enabled             bool     `json:"enabled"`
	ModelOrder          []string `json:"model_order"`
	ComplexityThreshold float64  `json:"complexity_threshold"`
}

type SemanticCacheConfig struct {
	Enabled             bool    `json:"enabled"`
	MinSamples          int     `json:"min_samples"`
	ConfidenceThreshold float64 `json:"confidence_threshold"`
	TTLSeconds          int     `json:"ttl_seconds"`
}

type SentinelConfig struct {
	Keys          map[string]Key             `json:"keys"`
	KeyInstances  map[string]KeyInstance     `json:"key_instances"`
	Models        map[string]ModelDefinition `json:"models"`
	RoutingPolicy RoutingPolicy              `json:"routing_policy"`
	Judge         JudgeConfig                `json:"judge"`
	SemanticCache SemanticCacheConfig        `json:"semantic_cache"`
}

func LoadRuntimeConfig(settings Settings) (*SentinelConfig, string, error) {
	if _, err := os.Stat(settings.SentinelConfigPath); err == nil {
		cfg, err := LoadSentinelConfig(settings.SentinelConfigPath)
		return cfg, "sentinel", err
	}
	cfg, err := LoadLegacyConfig(settings.ModelsConfigPath, settings)
	return cfg, "legacy", err
}

func LoadSentinelConfig(path string) (*SentinelConfig, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	data = resolveEnvPlaceholders(data)
	var cfg SentinelConfig
	if err := json.Unmarshal(data, &cfg); err != nil {
		return nil, err
	}
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	return &cfg, nil
}

func (c *SentinelConfig) Validate() error {
	if len(c.Keys) == 0 {
		return errors.New("keys must not be empty")
	}
	if len(c.KeyInstances) == 0 {
		return errors.New("key_instances must not be empty")
	}
	if len(c.Models) == 0 {
		return errors.New("models must not be empty")
	}
	for id, inst := range c.KeyInstances {
		if _, ok := c.Keys[inst.KeyRef]; !ok {
			return fmt.Errorf("key_instance %q references missing key %q", id, inst.KeyRef)
		}
	}
	for id, model := range c.Models {
		instances := model.KeyInstances
		if len(instances) == 0 && model.KeyInstance != "" {
			instances = []string{model.KeyInstance}
			model.KeyInstances = instances
			c.Models[id] = model
		}
		if len(instances) == 0 {
			return fmt.Errorf("model %q must define key_instance or key_instances", id)
		}
		seen := map[string]bool{}
		enabled := 0
		for _, instanceID := range instances {
			if seen[instanceID] {
				return fmt.Errorf("model %q has duplicate key_instance %q", id, instanceID)
			}
			seen[instanceID] = true
			inst, ok := c.KeyInstances[instanceID]
			if !ok {
				return fmt.Errorf("model %q references missing key_instance %q", id, instanceID)
			}
			key := c.Keys[inst.KeyRef]
			if key.Type != model.Provider {
				return fmt.Errorf("model %q provider %q does not match key provider %q", id, model.Provider, key.Type)
			}
			if inst.Enabled {
				enabled++
			}
		}
		if model.Enabled && enabled == 0 {
			return fmt.Errorf("model %q has no enabled key_instances", id)
		}
	}
	if len(c.RoutingPolicy.WeakTier.Order) == 0 {
		return errors.New("routing_policy.weak_tier.order must not be empty")
	}
	if len(c.RoutingPolicy.StrongTier.Order) == 0 {
		return errors.New("routing_policy.strong_tier.order must not be empty")
	}
	weak := map[string]bool{}
	for _, modelID := range c.RoutingPolicy.WeakTier.Order {
		model, ok := c.Models[modelID]
		if !ok {
			return fmt.Errorf("weak tier references missing model %q", modelID)
		}
		if !model.Enabled {
			return fmt.Errorf("weak tier references disabled model %q", modelID)
		}
		weak[modelID] = true
	}
	for _, modelID := range c.RoutingPolicy.StrongTier.Order {
		model, ok := c.Models[modelID]
		if !ok {
			return fmt.Errorf("strong tier references missing model %q", modelID)
		}
		if !model.Enabled {
			return fmt.Errorf("strong tier references disabled model %q", modelID)
		}
		if weak[modelID] {
			return fmt.Errorf("model %q cannot appear in both weak and strong tiers", modelID)
		}
	}
	if c.Judge.Enabled && len(c.Judge.ModelOrder) == 0 {
		return errors.New("judge.enabled is true but judge.model_order is empty")
	}
	for _, modelID := range c.Judge.ModelOrder {
		if _, ok := c.Models[modelID]; !ok {
			return fmt.Errorf("judge.model_order references missing model %q", modelID)
		}
	}
	return nil
}

func resolveEnvPlaceholders(data []byte) []byte {
	re := regexp.MustCompile(`\$\{([A-Z0-9_]+)\}`)
	return re.ReplaceAllFunc(data, func(match []byte) []byte {
		parts := re.FindSubmatch(match)
		if len(parts) != 2 {
			return match
		}
		value := os.Getenv(string(parts[1]))
		encoded, err := json.Marshal(value)
		if err != nil {
			return []byte(`""`)
		}
		return encoded[1 : len(encoded)-1]
	})
}

type legacyConfig struct {
	Models map[string]legacyModel `json:"models"`
}

type legacyModel struct {
	DisplayName string       `json:"display_name"`
	Provider    ProviderType `json:"provider"`
	ModelKey    string       `json:"model_key"`
	Status      string       `json:"status"`
	Routing     struct {
		PriorityGroup string `json:"priority_group"`
		Order         int    `json:"order"`
	} `json:"routing"`
	Limits  Limits `json:"limits"`
	Pricing struct {
		InputCostPerM  float64 `json:"input_cost_per_m"`
		OutputCostPerM float64 `json:"output_cost_per_m"`
	} `json:"pricing"`
}

func LoadLegacyConfig(path string, settings Settings) (*SentinelConfig, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var legacy legacyConfig
	if err := json.Unmarshal(data, &legacy); err != nil {
		return nil, err
	}
	cfg := &SentinelConfig{
		Keys:         map[string]Key{},
		KeyInstances: map[string]KeyInstance{},
		Models:       map[string]ModelDefinition{},
		Judge: JudgeConfig{
			Enabled:             true,
			ComplexityThreshold: settings.ComplexityThreshold,
		},
		SemanticCache: SemanticCacheConfig{
			Enabled:             true,
			MinSamples:          settings.SemanticCacheMinSamples,
			ConfidenceThreshold: settings.SemanticCacheConfidence,
			TTLSeconds:          settings.SemanticCacheTTLSeconds,
		},
	}
	weakItems := make([]legacyOrder, 0)
	strongItems := make([]legacyOrder, 0)
	judgeItems := make([]legacyOrder, 0)
	for id, model := range legacy.Models {
		if strings.ToUpper(model.Status) != "ACTIVE" {
			continue
		}
		keyID := string(model.Provider) + "_key"
		instanceID := string(model.Provider) + "_primary"
		if _, ok := cfg.Keys[keyID]; !ok {
			cfg.Keys[keyID] = Key{Type: model.Provider, Value: providerKeyValue(model.Provider, settings)}
			cfg.KeyInstances[instanceID] = KeyInstance{
				KeyRef:      keyID,
				Priority:    0,
				Enabled:     true,
				Description: "Primary " + string(model.Provider) + " key",
			}
		}
		cfg.Models[id] = ModelDefinition{
			Enabled:      true,
			Provider:     model.Provider,
			ModelID:      firstNonEmpty(model.ModelKey, id),
			KeyInstances: []string{instanceID},
			Pricing: Pricing{
				InputCostPerM:  model.Pricing.InputCostPerM,
				OutputCostPerM: model.Pricing.OutputCostPerM,
			},
			Limits:      model.Limits,
			DisplayName: firstNonEmpty(model.DisplayName, id),
		}
		item := legacyOrder{ID: id, Order: model.Routing.Order}
		switch model.Routing.PriorityGroup {
		case "strong_tier":
			strongItems = append(strongItems, item)
		default:
			weakItems = append(weakItems, item)
		}
		if model.Provider == ProviderGemini || strings.Contains(strings.ToLower(id), "judge") {
			judgeItems = append(judgeItems, item)
		}
	}
	sortLegacy(weakItems)
	sortLegacy(strongItems)
	sortLegacy(judgeItems)
	cfg.RoutingPolicy.WeakTier.Order = ids(weakItems)
	cfg.RoutingPolicy.StrongTier.Order = ids(strongItems)
	cfg.Judge.ModelOrder = ids(judgeItems)
	if len(cfg.Judge.ModelOrder) == 0 {
		for _, item := range weakItems {
			cfg.Judge.ModelOrder = append(cfg.Judge.ModelOrder, item.ID)
			if len(cfg.Judge.ModelOrder) == 2 {
				break
			}
		}
	}
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	return cfg, nil
}

type legacyOrder struct {
	ID    string
	Order int
}

func sortLegacy(items []legacyOrder) {
	sort.SliceStable(items, func(i, j int) bool {
		if items[i].Order == items[j].Order {
			return items[i].ID < items[j].ID
		}
		return items[i].Order < items[j].Order
	})
}

func ids(items []legacyOrder) []string {
	out := make([]string, 0, len(items))
	for _, item := range items {
		out = append(out, item.ID)
	}
	return out
}

func providerKeyValue(provider ProviderType, settings Settings) string {
	switch provider {
	case ProviderDeepSeek:
		return settings.DeepSeekAPIKey
	case ProviderAnthropic:
		return settings.AnthropicAPIKey
	case ProviderGemini:
		return firstNonEmpty(settings.GeminiBackup1APIKey, settings.GeminiBackup2APIKey)
	case ProviderGroq:
		return settings.GroqAPIKey
	case ProviderOpenRouter:
		return settings.OpenRouterAPIKey
	default:
		return ""
	}
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if value != "" {
			return value
		}
	}
	return ""
}
