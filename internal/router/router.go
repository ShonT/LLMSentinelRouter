package router

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"

	"github.com/ShonT/LLMSentinelRouter/internal/budget"
	"github.com/ShonT/LLMSentinelRouter/internal/config"
	"github.com/ShonT/LLMSentinelRouter/internal/cycle"
	"github.com/ShonT/LLMSentinelRouter/internal/judge"
	"github.com/ShonT/LLMSentinelRouter/internal/metrics"
	"github.com/ShonT/LLMSentinelRouter/internal/provider"
	"github.com/ShonT/LLMSentinelRouter/internal/rate"
	"github.com/ShonT/LLMSentinelRouter/internal/redaction"
	"github.com/ShonT/LLMSentinelRouter/internal/semantic"
	"github.com/ShonT/LLMSentinelRouter/internal/storage"
	"github.com/ShonT/LLMSentinelRouter/internal/threshold"
)

type Result struct {
	ModelUsed       string
	Response        provider.Response
	ComplexityScore float64
	ImpactScope     string
	Reasoning       string
	Cost            float64
	CostSource      string
	ComputedCost    *float64
	SessionCost     float64
	CycleDetected   bool
	DecisionReason  string
	Tier            string
	UseJudge        *bool
}

type Router struct {
	settings      config.Settings
	configManager *config.Manager
	store         *storage.Store
	budget        *budget.Manager
	threshold     *threshold.Dynamic
	cycles        *cycle.Registry
	cache         *semantic.Cache
	limiter       *rate.Limiter
	redactor      *redaction.Engine
	metrics       *metrics.Collector
	clientFactory provider.Factory
	judgeRegistry *judge.Registry
	mu            sync.RWMutex
	modelStatus   map[string]string
	modelStats    map[string]*ModelRuntime
}

// ModelStreamHandler receives streaming chunks after the routed model is selected.
type ModelStreamHandler func(modelID string, chunk provider.StreamChunk) error

type ModelRuntime struct {
	Status           string
	CurrentRPM       int
	RequestsToday    int
	TokensToday      int
	TotalCostSession float64
	LastUpdated      *time.Time
}

func New(settings config.Settings, manager *config.Manager, store *storage.Store, collector *metrics.Collector) *Router {
	health := judge.NewHealthTracker(settings.JudgeFailureThreshold, settings.JudgeCooldownSeconds)
	factory := provider.Factory{}
	return &Router{
		settings:      settings,
		configManager: manager,
		store:         store,
		budget:        budget.NewManager(store, settings.MaxCostPerSession),
		threshold:     threshold.New(settings.TargetEscalationRate, settings.RollingWindowSize, settings.InitialThreshold),
		cycles:        cycle.NewRegistry(1000, settings.CycleDetectionThreshold, settings.CycleDetectionWindowSize),
		cache:         semantic.NewCache(settings.SemanticCacheMinSamples, settings.SemanticCacheConfidence, settings.SemanticCacheTTLSeconds),
		limiter:       rate.New(0.95),
		redactor:      redaction.New(settings.RedactionMode, settings.RedactionStrategy, settings.RedactionSalt, settings.RedactionCategories),
		metrics:       collector,
		clientFactory: factory,
		judgeRegistry: judge.NewRegistry(nil, factory, health, settings.JudgeMaxAttempts),
		modelStatus:   map[string]string{},
		modelStats:    map[string]*ModelRuntime{},
	}
}

func (r *Router) Route(ctx context.Context, sessionID, clientIP, tier, prompt string, messages []provider.Message, useJudge *bool, opts provider.Options, stream ModelStreamHandler) (Result, error) {
	start := time.Now()
	if sessionID == "" {
		sessionID = NewID()
	}
	if tier == "" {
		tier = "free"
	}
	cfg := r.configManager.Current()
	if cfg == nil {
		return Result{}, errors.New("runtime config not loaded")
	}
	if _, err := r.budget.GetOrCreateSession(ctx, sessionID, clientIP, tier); err != nil {
		return Result{}, err
	}
	originalPrompt := prompt
	redactedMessages := messages
	redactionResult := r.redactor.Scrub(prompt)
	if r.redactor.ShouldRedactForLLM() {
		prompt = redactionResult.Text
		redactedMessages = scrubMessages(r.redactor, messages)
	}
	semanticEnabled := r.settings.SemanticCacheEnabled && cfg.SemanticCache.Enabled
	cacheRoute, cacheConfidence, cacheOK := "", 0.0, false
	if semanticEnabled {
		cacheRoute, cacheConfidence, cacheOK = r.cache.ConfidentRoute(prompt, redactedMessages)
	}
	semanticHash := semantic.HashPayload(prompt, redactedMessages)
	r.metrics.Record("semantic_cache", map[string]any{
		"event":          "lookup",
		"semantic_hash":  semanticHash,
		"hit":            cacheOK,
		"confidence":     cacheConfidence,
		"route_decision": cacheRoute,
	})
	const estimatedWorstCaseCost = 5.0
	if r.settings.EnableBudgetKillSwitch {
		if _, err := r.budget.RequireBudget(ctx, sessionID, estimatedWorstCaseCost); err != nil {
			return Result{}, err
		}
	}
	detector := r.cycles.Get(sessionID)
	cycleDetected := false
	if r.settings.EnableCycleDetection {
		cycleDetected = detector.DetectPrompt(prompt)
	}
	judgeResult := judge.Result{ComplexityScore: 0.0, ImpactScope: "LOW", Reasoning: "Judge deferred - conditional mode (will call if weak model is slow)"}
	judgeInvoked := false
	if cacheOK {
		if cacheRoute == "strong" {
			judgeResult = judge.Result{ComplexityScore: 0.95, ImpactScope: "HIGH", Reasoning: fmt.Sprintf("Judge skipped - cache confident (conf=%.2f) recommends strong model", cacheConfidence)}
		} else {
			judgeResult = judge.Result{ComplexityScore: 0.0, ImpactScope: "LOW", Reasoning: fmt.Sprintf("Judge skipped - cache confident (conf=%.2f) recommends weak model", cacheConfidence)}
		}
	} else if useJudge != nil && !*useJudge {
		judgeResult = judge.Result{ComplexityScore: 0.0, ImpactScope: "LOW", Reasoning: "Judge skipped by request (use_judge=false)"}
	} else if useJudge != nil && *useJudge {
		judgeInvoked = true
		judgeResult = r.evaluateJudge(ctx, cfg, prompt)
	}
	currentThreshold := r.threshold.Threshold()
	strictMode := r.settings.EnableDynamicThreshold && r.threshold.IsStrictMode()
	routeDecision := decideRoute(judgeResult.ComplexityScore, judgeResult.ImpactScope, currentThreshold, strictMode, cycleDetected)
	decisionReason := buildReason(routeDecision, judgeResult.ComplexityScore, judgeResult.ImpactScope, currentThreshold, strictMode, cycleDetected)
	priorityGroup := "fast_tier"
	resultTier := "weak"
	if routeDecision == "strong" {
		priorityGroup = "strong_tier"
		resultTier = "strong"
	}
	callCtx := ctx
	cancelCall := func() {}
	conditionalWeakCall := useJudge == nil && !cacheOK && routeDecision == "weak"
	if conditionalWeakCall {
		callCtx, cancelCall = context.WithTimeout(ctx, r.conditionalJudgeTimeout())
	}
	response, modelUsed, modelLatency, err := r.callCandidates(callCtx, cfg, priorityGroup, prompt, redactedMessages, opts, stream)
	cancelCall()
	if err != nil && conditionalWeakCall && contextTimedOut(err, callCtx) {
		judgeInvoked = true
		judgeResult = r.evaluateJudge(ctx, cfg, prompt)
		currentThreshold = r.threshold.Threshold()
		strictMode = r.settings.EnableDynamicThreshold && r.threshold.IsStrictMode()
		routeDecision = decideRoute(judgeResult.ComplexityScore, judgeResult.ImpactScope, currentThreshold, strictMode, cycleDetected)
		decisionReason = "Weak model exceeded conditional judge timeout; " + buildReason(routeDecision, judgeResult.ComplexityScore, judgeResult.ImpactScope, currentThreshold, strictMode, cycleDetected)
		if routeDecision == "strong" {
			priorityGroup = "strong_tier"
			resultTier = "strong"
		}
		response, modelUsed, modelLatency, err = r.callCandidates(ctx, cfg, priorityGroup, prompt, redactedMessages, opts, stream)
	}
	if err != nil {
		detector.ClearLastResponse()
		return Result{}, err
	}
	if response.Content != "" {
		detector.Add(prompt, response.Content)
	}
	finalCost, costSource, computedCost := finalCost(response)
	if err := r.budget.AddCost(ctx, sessionID, finalCost); err != nil {
		return Result{}, err
	}
	session, err := r.store.GetSessionRequired(ctx, sessionID)
	if err != nil {
		return Result{}, err
	}
	if r.settings.EnableDynamicThreshold {
		r.threshold.AddDecision(routeDecision == "strong")
		if _, changed := r.threshold.Adjust(); changed {
			r.metrics.Record("threshold_adjusted", map[string]any{"session_id": sessionID, "escalation_rate": r.threshold.Rate()})
		}
	}
	logPrompt := prompt
	logMessages := redactedMessages
	responseContentForLog := response.Content
	if r.redactor.ShouldRedactForLogs() && !r.redactor.ShouldRedactForLLM() {
		logPrompt = r.redactor.Scrub(originalPrompt).Text
		logMessages = scrubMessages(r.redactor, messages)
		responseContentForLog = r.redactor.Scrub(response.Content).Text
	}
	requestID := NewID()
	requestLatency := float64(time.Since(start).Milliseconds())
	if err := r.store.InsertRoutingDecision(ctx, storage.RoutingDecision{
		SessionID:        sessionID,
		RequestID:        requestID,
		Timestamp:        time.Now().UTC(),
		ModelUsed:        modelUsed,
		ComplexityScore:  judgeResult.ComplexityScore,
		CostIncurred:     finalCost,
		CostSource:       costSource,
		ComputedCost:     nullableFloat(computedCost),
		PromptHash:       shortHash(logPrompt),
		ImpactScope:      nullableString(judgeResult.ImpactScope),
		Reason:           nullableString(decisionReason),
		InputTokens:      response.Usage.PromptTokens,
		OutputTokens:     response.Usage.CompletionTokens,
		TotalTokens:      response.Usage.TotalTokens,
		RequestLatencyMS: requestLatency,
		ModelLatencyMS:   modelLatency,
		JudgeLatencyMS:   nullableFloat(&judgeResult.LatencyMS),
	}); err != nil {
		return Result{}, err
	}
	if semanticEnabled && !cycleDetected {
		r.cache.Record(logPrompt, logMessages, modelUsed, routeDecision, requestLatency, judgeInvoked, finalCost, response.Usage.TotalTokens)
	}
	r.limiter.Record(modelUsed, response.Usage.TotalTokens)
	r.recordModelRuntime(modelUsed, response.Usage.TotalTokens, finalCost)
	r.metrics.Record("routing_decision", map[string]any{
		"session_id":       sessionID,
		"request_id":       requestID,
		"model_used":       modelUsed,
		"route":            routeDecision,
		"latency_ms":       requestLatency,
		"model_latency_ms": modelLatency,
		"cost":             finalCost,
		"cycle_detected":   cycleDetected,
		"response_preview": truncate(responseContentForLog, 500),
	})
	return Result{
		ModelUsed:       modelUsed,
		Response:        response,
		ComplexityScore: judgeResult.ComplexityScore,
		ImpactScope:     judgeResult.ImpactScope,
		Reasoning:       judgeResult.Reasoning,
		Cost:            finalCost,
		CostSource:      costSource,
		ComputedCost:    computedCost,
		SessionCost:     session.CurrentCost,
		CycleDetected:   cycleDetected,
		DecisionReason:  decisionReason,
		Tier:            resultTier,
		UseJudge:        useJudge,
	}, nil
}

func (r *Router) ResetSemanticCache() {
	r.cache.Reset()
}

func (r *Router) ResetEscalation() {
	r.threshold.Reset(nil)
}

func (r *Router) UpdatePolicy(settings config.Settings) {
	r.settings = settings
	r.budget.SetMaxCostPerSession(settings.MaxCostPerSession)
	r.threshold = threshold.New(settings.TargetEscalationRate, settings.RollingWindowSize, settings.InitialThreshold)
	r.cycles = cycle.NewRegistry(1000, settings.CycleDetectionThreshold, settings.CycleDetectionWindowSize)
	r.cache = semantic.NewCache(settings.SemanticCacheMinSamples, settings.SemanticCacheConfidence, settings.SemanticCacheTTLSeconds)
	r.redactor = redaction.New(settings.RedactionMode, settings.RedactionStrategy, settings.RedactionSalt, settings.RedactionCategories)
}

func (r *Router) conditionalJudgeTimeout() time.Duration {
	timeout := time.Duration(r.settings.ConditionalJudgeTimeout * float64(time.Second))
	if timeout <= 0 {
		return 15 * time.Second
	}
	return timeout
}

func (r *Router) SetModelStatus(modelID, status string) {
	if status == "" {
		status = "active"
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	r.modelStatus[modelID] = status
}

func (r *Router) SetAllModelStatus(cfg *config.SentinelConfig, status string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	for modelID := range cfg.Models {
		r.modelStatus[modelID] = status
	}
}

func (r *Router) ResetModelCost(modelID string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	stats := r.modelStats[modelID]
	if stats == nil {
		stats = &ModelRuntime{}
		r.modelStats[modelID] = stats
	}
	stats.TotalCostSession = 0
	now := time.Now().UTC()
	stats.LastUpdated = &now
}

func (r *Router) RuntimeFor(modelID string, model config.ModelDefinition) ModelRuntime {
	r.mu.RLock()
	defer r.mu.RUnlock()
	status := r.modelStatus[modelID]
	if !model.Enabled {
		status = "disabled"
	} else if status == "" {
		status = "active"
	}
	stats := ModelRuntime{Status: status}
	if current := r.modelStats[modelID]; current != nil {
		stats = *current
		stats.Status = status
	}
	stats.CurrentRPM = r.limiter.Usage(modelID).RequestsLastMinute
	return stats
}

func (r *Router) evaluateJudge(ctx context.Context, cfg *config.SentinelConfig, prompt string) judge.Result {
	return r.judgeRegistry.Evaluate(ctx, cfg, prompt)
}

func (r *Router) JudgeRegistryStatus() []map[string]any {
	cfg := r.configManager.Current()
	if cfg == nil {
		return nil
	}
	return r.judgeRegistry.RegistryStatus(cfg)
}

func (r *Router) callCandidates(ctx context.Context, cfg *config.SentinelConfig, priorityGroup, prompt string, messages []provider.Message, opts provider.Options, stream ModelStreamHandler) (provider.Response, string, float64, error) {
	candidates := r.candidates(cfg, priorityGroup)
	if len(candidates) == 0 {
		return provider.Response{}, "", 0, fmt.Errorf("no active models in priority group %s", priorityGroup)
	}
	var lastErr error
	for _, modelID := range candidates {
		model := cfg.Models[modelID]
		estimatedTokens := len(strings.Fields(prompt)) * 2
		allowed, reason, usage := r.limiter.Check(modelID, model.Limits.RequestsPerMinute, model.Limits.TokensPerMinute, model.Limits.RequestsPerDay, model.Limits.TokensPerDay, estimatedTokens)
		if !allowed {
			r.metrics.Record("rate_limit_preemptive_skip", map[string]any{"model_id": modelID, "reason": reason, "usage": usage})
			continue
		}
		for _, key := range orderedKeys(cfg, model) {
			client := r.clientFactory.NewClient(model.Provider, key, model)
			start := time.Now()
			var response provider.Response
			var err error
			if opts.Stream && stream != nil {
				handler := func(chunk provider.StreamChunk) error {
					return stream(modelID, chunk)
				}
				response, err = client.ChatCompletionStream(ctx, messages, opts, handler)
			} else {
				response, err = client.ChatCompletion(ctx, messages, opts)
			}
			_ = client.Close()
			latency := float64(time.Since(start).Milliseconds())
			if err == nil {
				if response.Model == "" {
					response.Model = model.ModelID
				}
				return response, modelID, latency, nil
			}
			lastErr = err
			r.metrics.Record("model_call_error", map[string]any{"model_id": modelID, "error": err.Error()})
		}
	}
	if lastErr == nil {
		lastErr = errors.New("no model could handle request")
	}
	return provider.Response{}, "", 0, lastErr
}

func (r *Router) candidates(cfg *config.SentinelConfig, priorityGroup string) []string {
	var order []string
	if priorityGroup == "strong_tier" {
		order = cfg.RoutingPolicy.StrongTier.Order
	} else {
		order = cfg.RoutingPolicy.WeakTier.Order
	}
	out := make([]string, 0, len(order))
	for _, modelID := range order {
		if model, ok := cfg.Models[modelID]; ok && r.modelCanRoute(modelID, model) {
			out = append(out, modelID)
		}
	}
	return out
}

func (r *Router) modelCanRoute(modelID string, model config.ModelDefinition) bool {
	if !model.Enabled {
		return false
	}
	r.mu.RLock()
	status := r.modelStatus[modelID]
	r.mu.RUnlock()
	return status == "" || status == "active"
}

func (r *Router) recordModelRuntime(modelID string, tokens int, cost float64) {
	r.mu.Lock()
	defer r.mu.Unlock()
	stats := r.modelStats[modelID]
	if stats == nil {
		stats = &ModelRuntime{Status: "active"}
		r.modelStats[modelID] = stats
	}
	stats.RequestsToday++
	stats.TokensToday += tokens
	stats.TotalCostSession += cost
	now := time.Now().UTC()
	stats.LastUpdated = &now
}

func contextTimedOut(err error, ctx context.Context) bool {
	return errors.Is(err, context.DeadlineExceeded) || errors.Is(ctx.Err(), context.DeadlineExceeded)
}

func orderedKeys(cfg *config.SentinelConfig, model config.ModelDefinition) []string {
	instances := model.KeyInstances
	if len(instances) == 0 && model.KeyInstance != "" {
		instances = []string{model.KeyInstance}
	}
	type item struct {
		priority int
		value    string
	}
	items := make([]item, 0, len(instances))
	for _, id := range instances {
		inst, ok := cfg.KeyInstances[id]
		if !ok || !inst.Enabled {
			continue
		}
		key, ok := cfg.Keys[inst.KeyRef]
		if !ok || key.Value == "" {
			continue
		}
		items = append(items, item{priority: inst.Priority, value: key.Value})
	}
	for i := 0; i < len(items); i++ {
		for j := i + 1; j < len(items); j++ {
			if items[j].priority < items[i].priority {
				items[i], items[j] = items[j], items[i]
			}
		}
	}
	out := make([]string, 0, len(items))
	for _, item := range items {
		out = append(out, item.value)
	}
	return out
}

func decideRoute(score float64, impact string, thresholdValue float64, strictMode, cycleDetected bool) string {
	if cycleDetected {
		return "strong"
	}
	effectiveScore := score
	if strictMode {
		effectiveScore = score - 0.15
	}
	if effectiveScore < thresholdValue {
		return "weak"
	}
	if strictMode && impact != "HIGH" {
		return "weak"
	}
	return "strong"
}

func buildReason(route string, score float64, impact string, thresholdValue float64, strictMode, cycleDetected bool) string {
	if cycleDetected {
		return "Cycle detected - forced strong model."
	}
	if score >= thresholdValue {
		if strictMode && impact != "HIGH" {
			return fmt.Sprintf("complexity_score %.3f >= threshold %.3f; strict mode and impact_scope not HIGH -> downgraded", score, thresholdValue)
		}
		return fmt.Sprintf("complexity_score %.3f >= threshold %.3f; impact_scope %s", score, thresholdValue, impact)
	}
	return fmt.Sprintf("complexity_score %.3f < threshold %.3f", score, thresholdValue)
}

func finalCost(response provider.Response) (float64, string, *float64) {
	if response.Cost >= 0 {
		return response.Cost, "provider", nil
	}
	computed := 0.0
	return computed, "computed", &computed
}

func scrubMessages(engine *redaction.Engine, messages []provider.Message) []provider.Message {
	out := make([]provider.Message, len(messages))
	for i, msg := range messages {
		out[i] = msg
		out[i].Content = engine.Scrub(msg.Content).Text
	}
	return out
}

func shortHash(value string) string {
	sum := sha256.Sum256([]byte(value))
	return hex.EncodeToString(sum[:4])
}

func nullableString(value string) sql.NullString {
	return sql.NullString{String: value, Valid: value != ""}
}

func nullableFloat(value *float64) sql.NullFloat64 {
	if value == nil {
		return sql.NullFloat64{}
	}
	return sql.NullFloat64{Float64: *value, Valid: true}
}

func truncate(value string, maxLen int) string {
	if len(value) <= maxLen {
		return value
	}
	return value[:maxLen]
}

func NewID() string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		now := time.Now().UnixNano()
		return fmt.Sprintf("%x", now)
	}
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:])
}
