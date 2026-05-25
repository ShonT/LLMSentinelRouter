package config

import (
	"os"
	"strconv"
	"strings"
)

type Settings struct {
	DeepSeekAPIKey           string
	AnthropicAPIKey          string
	GeminiBackup1APIKey      string
	GeminiBackup2APIKey      string
	GroqAPIKey               string
	OpenRouterAPIKey         string
	WeakModelID              string
	StrongModelID            string
	MaxCostPerSession        float64
	InitialThreshold         float64
	EscalationRateLimit      float64
	ComplexityThreshold      float64
	ConditionalJudgeTimeout  float64
	TargetEscalationRate     float64
	RollingWindowSize        int
	CORSOrigins              string
	DatabaseURL              string
	LogLevel                 string
	LogFile                  string
	AdminAPIToken            string
	ModelsConfigPath         string
	SentinelConfigPath       string
	EnableBudgetKillSwitch   bool
	EnableCycleDetection     bool
	EnableDynamicThreshold   bool
	CycleDetectionWindowSize int
	CycleDetectionThreshold  int
	RedactionMode            string
	RedactionStrategy        string
	RedactionSalt            string
	RedactionCategories      []string
	SemanticCacheEnabled     bool
	SemanticCacheMinSamples  int
	SemanticCacheConfidence  float64
	SemanticCacheTTLSeconds  int
	Host                     string
	Port                     string
	DashboardPort            string
	JudgeFailureThreshold    int
	JudgeCooldownSeconds     int
	JudgeMaxAttempts         int
}

func LoadSettings() Settings {
	return Settings{
		DeepSeekAPIKey:           envString("DEEPSEEK_API_KEY", ""),
		AnthropicAPIKey:          envString("ANTHROPIC_API_KEY", ""),
		GeminiBackup1APIKey:      envString("GEMINI_BACKUP1_API_KEY", envString("GEMINI_API_KEY", "")),
		GeminiBackup2APIKey:      envString("GEMINI_BACKUP2_API_KEY", envString("GEMINI_API_KEY", "")),
		GroqAPIKey:               envString("GROQ_API_KEY", ""),
		OpenRouterAPIKey:         envString("OPENROUTER_API_KEY", ""),
		WeakModelID:              envString("WEAK_MODEL_ID", "deepseek-chat"),
		StrongModelID:            envString("STRONG_MODEL_ID", "claude-3-opus-20240229"),
		MaxCostPerSession:        envFloat("MAX_COST_PER_SESSION", 10.0),
		InitialThreshold:         envFloat("INITIAL_THRESHOLD", 0.7),
		EscalationRateLimit:      envFloat("ESCALATION_RATE_LIMIT", 0.05),
		ComplexityThreshold:      envFloat("COMPLEXITY_THRESHOLD", 0.5),
		ConditionalJudgeTimeout:  envFloat("CONDITIONAL_JUDGE_TIMEOUT_SECONDS", 15.0),
		TargetEscalationRate:     envFloat("TARGET_ESCALATION_RATE", 0.05),
		RollingWindowSize:        envInt("ROLLING_WINDOW_SIZE", 20),
		CORSOrigins:              envString("CORS_ORIGINS", "*"),
		DatabaseURL:              envString("DATABASE_URL", "sqlite:///./data/sentinelrouter.db"),
		LogLevel:                 envString("LOG_LEVEL", "INFO"),
		LogFile:                  envString("LOG_FILE", "./logs/sentinelrouter.log"),
		AdminAPIToken:            envString("ADMIN_API_TOKEN", ""),
		ModelsConfigPath:         envString("MODELS_CONFIG_PATH", "./config/models_config.json"),
		SentinelConfigPath:       envString("SENTINEL_CONFIG_PATH", "./config/sentinel_config.json"),
		EnableBudgetKillSwitch:   envBool("ENABLE_BUDGET_KILLSWITCH", true),
		EnableCycleDetection:     envBool("ENABLE_CYCLE_DETECTION", true),
		EnableDynamicThreshold:   envBool("ENABLE_DYNAMIC_THRESHOLD", true),
		CycleDetectionWindowSize: envInt("CYCLE_DETECTION_WINDOW_SIZE", 50),
		CycleDetectionThreshold:  envInt("CYCLE_DETECTION_SIMHASH_THRESHOLD", 3),
		RedactionMode:            strings.ToLower(envString("REDACTION_MODE", "logs")),
		RedactionStrategy:        strings.ToLower(envString("REDACTION_STRATEGY", "simple")),
		RedactionSalt:            envString("REDACTION_SALT", "sentinelrouter"),
		RedactionCategories:      envList("REDACTION_ENABLED_CATEGORIES"),
		SemanticCacheEnabled:     envBool("SEMANTIC_CACHE_ENABLED", true),
		SemanticCacheMinSamples:  envInt("SEMANTIC_CACHE_MIN_SAMPLES", 3),
		SemanticCacheConfidence:  envFloat("SEMANTIC_CACHE_CONFIDENCE_THRESHOLD", 0.75),
		SemanticCacheTTLSeconds:  envInt("SEMANTIC_CACHE_TTL_SECONDS", 604800),
		Host:                     envString("HOST", "0.0.0.0"),
		Port:                     envString("PORT", "8000"),
		DashboardPort:            envString("DASHBOARD_PORT", "8001"),
		JudgeFailureThreshold:    envInt("JUDGE_FAILURE_THRESHOLD", 3),
		JudgeCooldownSeconds:     envInt("JUDGE_COOLDOWN_SECONDS", 60),
		JudgeMaxAttempts:         envInt("JUDGE_MAX_ATTEMPTS", 3),
	}
}

func envString(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func envFloat(key string, fallback float64) float64 {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	parsed, err := strconv.ParseFloat(value, 64)
	if err != nil {
		return fallback
	}
	return parsed
}

func envInt(key string, fallback int) int {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	parsed, err := strconv.Atoi(value)
	if err != nil {
		return fallback
	}
	return parsed
}

func envBool(key string, fallback bool) bool {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	parsed, err := strconv.ParseBool(value)
	if err != nil {
		return fallback
	}
	return parsed
}

func envList(key string) []string {
	raw := os.Getenv(key)
	if raw == "" {
		return nil
	}
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part != "" {
			out = append(out, part)
		}
	}
	return out
}
