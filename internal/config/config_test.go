package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLoadSettingsDefaults(t *testing.T) {
	settings := LoadSettings()
	if settings.MaxCostPerSession != 10.0 {
		t.Fatalf("max_cost = %g, want 10", settings.MaxCostPerSession)
	}
	if settings.Port != "8000" {
		t.Fatalf("port = %q, want 8000", settings.Port)
	}
	if settings.DashboardPort != "8001" {
		t.Fatalf("dashboard_port = %q, want 8001", settings.DashboardPort)
	}
	if settings.InitialThreshold != 0.7 {
		t.Fatalf("threshold = %g, want 0.7", settings.InitialThreshold)
	}
	if !settings.EnableBudgetKillSwitch {
		t.Fatal("budget killswitch should default to true")
	}
	if !settings.EnableCycleDetection {
		t.Fatal("cycle detection should default to true")
	}
	if !settings.SemanticCacheEnabled {
		t.Fatal("semantic cache should default to true")
	}
	if settings.JudgeFailureThreshold != 3 {
		t.Fatalf("judge failure threshold = %d, want 3", settings.JudgeFailureThreshold)
	}
}

func TestLoadSettingsFromEnv(t *testing.T) {
	t.Setenv("MAX_COST_PER_SESSION", "25.0")
	t.Setenv("PORT", "9000")
	t.Setenv("ENABLE_BUDGET_KILLSWITCH", "false")

	settings := LoadSettings()
	if settings.MaxCostPerSession != 25.0 {
		t.Fatalf("max_cost = %g, want 25", settings.MaxCostPerSession)
	}
	if settings.Port != "9000" {
		t.Fatalf("port = %q, want 9000", settings.Port)
	}
	if settings.EnableBudgetKillSwitch {
		t.Fatal("budget killswitch should be false")
	}
}

func TestValidateMinimalConfig(t *testing.T) {
	cfg := &SentinelConfig{
		Keys:         map[string]Key{"k1": {Type: "deepseek", Value: "test-key"}},
		KeyInstances: map[string]KeyInstance{"ki1": {KeyRef: "k1", Enabled: true}},
		Models: map[string]ModelDefinition{
			"weak":   {Enabled: true, Provider: "deepseek", ModelID: "m1", KeyInstances: []string{"ki1"}},
			"strong": {Enabled: true, Provider: "deepseek", ModelID: "m2", KeyInstances: []string{"ki1"}},
		},
		RoutingPolicy: RoutingPolicy{
			WeakTier:   RoutingTier{Order: []string{"weak"}},
			StrongTier: RoutingTier{Order: []string{"strong"}},
		},
	}
	if err := cfg.Validate(); err != nil {
		t.Fatalf("valid config rejected: %v", err)
	}
}

func TestValidateRejectsEmptyKeys(t *testing.T) {
	cfg := &SentinelConfig{
		Keys:         map[string]Key{},
		KeyInstances: map[string]KeyInstance{"ki1": {KeyRef: "k1", Enabled: true}},
		Models:       map[string]ModelDefinition{"m": {Enabled: true}},
	}
	err := cfg.Validate()
	if err == nil {
		t.Fatal("should reject empty keys")
	}
}

func TestValidateRejectsOverlappingTiers(t *testing.T) {
	cfg := &SentinelConfig{
		Keys:         map[string]Key{"k1": {Type: "deepseek", Value: "key"}},
		KeyInstances: map[string]KeyInstance{"ki1": {KeyRef: "k1", Enabled: true}},
		Models: map[string]ModelDefinition{
			"model-a": {Enabled: true, Provider: "deepseek", ModelID: "m", KeyInstances: []string{"ki1"}},
		},
		RoutingPolicy: RoutingPolicy{
			WeakTier:   RoutingTier{Order: []string{"model-a"}},
			StrongTier: RoutingTier{Order: []string{"model-a"}},
		},
	}
	err := cfg.Validate()
	if err == nil {
		t.Fatal("should reject model in both tiers")
	}
}

func TestValidateRejectsMissingKeyInstance(t *testing.T) {
	cfg := &SentinelConfig{
		Keys:         map[string]Key{"k1": {Type: "deepseek", Value: "key"}},
		KeyInstances: map[string]KeyInstance{"ki1": {KeyRef: "k1", Enabled: true}},
		Models: map[string]ModelDefinition{
			"weak":   {Enabled: true, Provider: "deepseek", ModelID: "m1", KeyInstances: []string{"missing"}},
			"strong": {Enabled: true, Provider: "deepseek", ModelID: "m2", KeyInstances: []string{"ki1"}},
		},
		RoutingPolicy: RoutingPolicy{
			WeakTier:   RoutingTier{Order: []string{"weak"}},
			StrongTier: RoutingTier{Order: []string{"strong"}},
		},
	}
	err := cfg.Validate()
	if err == nil {
		t.Fatal("should reject missing key_instance reference")
	}
}

func TestValidateRejectsProviderMismatch(t *testing.T) {
	cfg := &SentinelConfig{
		Keys:         map[string]Key{"k1": {Type: "anthropic", Value: "key"}},
		KeyInstances: map[string]KeyInstance{"ki1": {KeyRef: "k1", Enabled: true}},
		Models: map[string]ModelDefinition{
			"weak":   {Enabled: true, Provider: "deepseek", ModelID: "m1", KeyInstances: []string{"ki1"}},
			"strong": {Enabled: true, Provider: "deepseek", ModelID: "m2", KeyInstances: []string{"ki1"}},
		},
		RoutingPolicy: RoutingPolicy{
			WeakTier:   RoutingTier{Order: []string{"weak"}},
			StrongTier: RoutingTier{Order: []string{"strong"}},
		},
	}
	err := cfg.Validate()
	if err == nil {
		t.Fatal("should reject provider mismatch")
	}
}

func TestValidateJudgeWithEmptyOrder(t *testing.T) {
	cfg := &SentinelConfig{
		Keys:         map[string]Key{"k1": {Type: "deepseek", Value: "key"}},
		KeyInstances: map[string]KeyInstance{"ki1": {KeyRef: "k1", Enabled: true}},
		Models: map[string]ModelDefinition{
			"weak":   {Enabled: true, Provider: "deepseek", ModelID: "m1", KeyInstances: []string{"ki1"}},
			"strong": {Enabled: true, Provider: "deepseek", ModelID: "m2", KeyInstances: []string{"ki1"}},
		},
		RoutingPolicy: RoutingPolicy{
			WeakTier:   RoutingTier{Order: []string{"weak"}},
			StrongTier: RoutingTier{Order: []string{"strong"}},
		},
		Judge: JudgeConfig{Enabled: true, ModelOrder: []string{}},
	}
	err := cfg.Validate()
	if err == nil {
		t.Fatal("should reject enabled judge with empty model_order")
	}
}

func TestLoadSentinelConfig(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "test_config.json")
	content := `{
  "keys": {"k1": {"type": "deepseek", "value": "test-key-12345678"}},
  "key_instances": {"ki1": {"key_ref": "k1", "priority": 0, "enabled": true}},
  "models": {
    "weak": {"enabled": true, "provider": "deepseek", "model_id": "m1", "key_instances": ["ki1"], "pricing": {"input_cost_per_m": 0.1, "output_cost_per_m": 0.2}, "limits": {"requests_per_minute": 60}},
    "strong": {"enabled": true, "provider": "deepseek", "model_id": "m2", "key_instances": ["ki1"], "pricing": {"input_cost_per_m": 1.0, "output_cost_per_m": 2.0}, "limits": {"requests_per_minute": 30}}
  },
  "routing_policy": {"weak_tier": {"order": ["weak"]}, "strong_tier": {"order": ["strong"]}},
  "judge": {"enabled": false},
  "semantic_cache": {"enabled": true, "min_samples": 3, "confidence_threshold": 0.75, "ttl_seconds": 604800}
}`
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("write: %v", err)
	}
	cfg, err := LoadSentinelConfig(path)
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if len(cfg.Models) != 2 {
		t.Fatalf("models = %d", len(cfg.Models))
	}
	if cfg.RoutingPolicy.WeakTier.Order[0] != "weak" {
		t.Fatalf("weak tier = %v", cfg.RoutingPolicy.WeakTier.Order)
	}
}

func TestEnvPlaceholderResolution(t *testing.T) {
	t.Setenv("TEST_API_KEY", "resolved-key")
	dir := t.TempDir()
	path := filepath.Join(dir, "test_config.json")
	content := `{
  "keys": {"k1": {"type": "deepseek", "value": "${TEST_API_KEY}"}},
  "key_instances": {"ki1": {"key_ref": "k1", "priority": 0, "enabled": true}},
  "models": {
    "weak": {"enabled": true, "provider": "deepseek", "model_id": "m1", "key_instances": ["ki1"], "pricing": {"input_cost_per_m": 0.1, "output_cost_per_m": 0.2}, "limits": {"requests_per_minute": 60}},
    "strong": {"enabled": true, "provider": "deepseek", "model_id": "m2", "key_instances": ["ki1"], "pricing": {"input_cost_per_m": 1.0, "output_cost_per_m": 2.0}, "limits": {"requests_per_minute": 30}}
  },
  "routing_policy": {"weak_tier": {"order": ["weak"]}, "strong_tier": {"order": ["strong"]}}
}`
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("write: %v", err)
	}
	cfg, err := LoadSentinelConfig(path)
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if cfg.Keys["k1"].Value != "resolved-key" {
		t.Fatalf("key value = %q, want resolved-key", cfg.Keys["k1"].Value)
	}
}

func TestConfigManagerReload(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "sentinel_config.json")
	content := `{
  "keys": {"k1": {"type": "deepseek", "value": "original-key"}},
  "key_instances": {"ki1": {"key_ref": "k1", "priority": 0, "enabled": true}},
  "models": {
    "weak": {"enabled": true, "provider": "deepseek", "model_id": "m1", "key_instances": ["ki1"], "pricing": {"input_cost_per_m": 0.1, "output_cost_per_m": 0.2}, "limits": {"requests_per_minute": 60}},
    "strong": {"enabled": true, "provider": "deepseek", "model_id": "m2", "key_instances": ["ki1"], "pricing": {"input_cost_per_m": 1.0, "output_cost_per_m": 2.0}, "limits": {"requests_per_minute": 30}}
  },
  "routing_policy": {"weak_tier": {"order": ["weak"]}, "strong_tier": {"order": ["strong"]}}
}`
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("write: %v", err)
	}
	settings := LoadSettings()
	settings.SentinelConfigPath = path
	settings.ModelsConfigPath = filepath.Join(dir, "missing.json")

	manager, err := NewManager(settings)
	if err != nil {
		t.Fatalf("new manager: %v", err)
	}
	cfg := manager.Current()
	if cfg.Keys["k1"].Value != "original-key" {
		t.Fatalf("initial key = %q", cfg.Keys["k1"].Value)
	}

	updated := `{
  "keys": {"k1": {"type": "deepseek", "value": "updated-key"}},
  "key_instances": {"ki1": {"key_ref": "k1", "priority": 0, "enabled": true}},
  "models": {
    "weak": {"enabled": true, "provider": "deepseek", "model_id": "m1", "key_instances": ["ki1"], "pricing": {"input_cost_per_m": 0.1, "output_cost_per_m": 0.2}, "limits": {"requests_per_minute": 60}},
    "strong": {"enabled": true, "provider": "deepseek", "model_id": "m2", "key_instances": ["ki1"], "pricing": {"input_cost_per_m": 1.0, "output_cost_per_m": 2.0}, "limits": {"requests_per_minute": 30}}
  },
  "routing_policy": {"weak_tier": {"order": ["weak"]}, "strong_tier": {"order": ["strong"]}}
}`
	if err := os.WriteFile(path, []byte(updated), 0o644); err != nil {
		t.Fatalf("rewrite: %v", err)
	}
	changed, err := manager.ReloadIfChanged()
	if err != nil {
		t.Fatalf("reload: %v", err)
	}
	if !changed {
		t.Fatal("should detect changed config")
	}
	if manager.Current().Keys["k1"].Value != "updated-key" {
		t.Fatalf("reloaded key = %q", manager.Current().Keys["k1"].Value)
	}
}

func TestModelDefinitionDefaultsEnabledTrue(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "test_config.json")
	content := `{
  "keys": {"k1": {"type": "deepseek", "value": "test-key-12345678"}},
  "key_instances": {"ki1": {"key_ref": "k1", "priority": 0}},
  "models": {
    "weak": {"provider": "deepseek", "model_id": "m1", "key_instances": ["ki1"], "pricing": {"input_cost_per_m": 0.1, "output_cost_per_m": 0.2}, "limits": {"requests_per_minute": 60}},
    "strong": {"provider": "deepseek", "model_id": "m2", "key_instances": ["ki1"], "pricing": {"input_cost_per_m": 1.0, "output_cost_per_m": 2.0}, "limits": {"requests_per_minute": 30}}
  },
  "routing_policy": {"weak_tier": {"order": ["weak"]}, "strong_tier": {"order": ["strong"]}}
}`
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("write: %v", err)
	}
	cfg, err := LoadSentinelConfig(path)
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if !cfg.Models["weak"].Enabled {
		t.Fatal("model should default to enabled=true")
	}
	if !cfg.KeyInstances["ki1"].Enabled {
		t.Fatal("key_instance should default to enabled=true")
	}
}
