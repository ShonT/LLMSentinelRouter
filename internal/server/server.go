package server

import (
	"context"
	"crypto/sha256"
	"crypto/subtle"
	"database/sql"
	_ "embed"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/ShonT/LLMSentinelRouter/internal/config"
	"github.com/ShonT/LLMSentinelRouter/internal/metrics"
	"github.com/ShonT/LLMSentinelRouter/internal/provider"
	"github.com/ShonT/LLMSentinelRouter/internal/router"
	"github.com/ShonT/LLMSentinelRouter/internal/storage"
)

//go:embed dashboard.html
var dashboardHTML string

type Server struct {
	settings        config.Settings
	configManager   *config.Manager
	store           *storage.Store
	router          *router.Router
	metrics         *metrics.Collector
	sessionDefaults SessionDefaults
	mu              sync.Mutex
}

type SessionDefaults struct {
	DefaultSessionID  string `json:"default_session_id"`
	DefaultTier       string `json:"default_tier"`
	DefaultUseJudge   *bool  `json:"default_use_judge"`
	SessionIDStrategy string `json:"session_id_strategy"`
}

const (
	sessionDefaultsStateKey = "session_defaults"
	adminPolicyStateKey     = "admin_policy"
)

type persistedPolicy struct {
	MaxCostPerSession        float64 `json:"max_cost_per_session"`
	EscalationRateLimit      float64 `json:"escalation_rate_limit"`
	TargetEscalationRate     float64 `json:"target_escalation_rate"`
	RollingWindowSize        int     `json:"rolling_window_size"`
	ComplexityThreshold      float64 `json:"complexity_threshold"`
	SemanticCacheEnabled     bool    `json:"semantic_cache_enabled"`
	SemanticCacheMinSamples  int     `json:"semantic_cache_min_samples"`
	SemanticCacheConfidence  float64 `json:"semantic_cache_confidence"`
	SemanticCacheTTLSeconds  int     `json:"semantic_cache_ttl_seconds"`
	EnableCycleDetection     bool    `json:"enable_cycle_detection"`
	CycleDetectionWindowSize int     `json:"cycle_detection_window_size"`
	CycleDetectionThreshold  int     `json:"cycle_detection_threshold"`
}

func New(settings config.Settings, manager *config.Manager, store *storage.Store, collector *metrics.Collector) *Server {
	defaults := SessionDefaults{
		DefaultSessionID:  "default-uuid-001",
		DefaultTier:       "free",
		SessionIDStrategy: "uuid",
	}
	settings, defaults = loadPersistedRuntimeState(store, settings, defaults)
	return &Server{
		settings:        settings,
		configManager:   manager,
		store:           store,
		router:          router.New(settings, manager, store, collector),
		metrics:         collector,
		sessionDefaults: defaults,
	}
}

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", s.health)
	mux.HandleFunc("GET /v1/models", s.models)
	mux.HandleFunc("GET /metrics", s.metricsSummary)
	mux.HandleFunc("GET /sessions/{session_id}", s.session)
	mux.HandleFunc("GET /audit/{session_id}", s.audit)
	mux.HandleFunc("POST /v1/chat/completions", s.chatCompletions)
	mux.HandleFunc("GET /api/dashboard/session-defaults", s.getSessionDefaults)
	mux.HandleFunc("POST /api/dashboard/session-defaults", s.updateSessionDefaults)
	mux.HandleFunc("POST /api/dashboard/regenerate-session-id", s.regenerateSessionID)
	mux.HandleFunc("GET /api/dashboard/live", s.dashboardLive)
	mux.HandleFunc("POST /api/dashboard/model/{model_id}/reset-cost", s.dashboardResetModelCost)
	mux.HandleFunc("POST /api/dashboard/model/{model_id}/status", s.dashboardModelStatus)
	mux.HandleFunc("POST /api/dashboard/reset-all-costs", s.dashboardResetAllCosts)
	mux.HandleFunc("POST /api/dashboard/start-all", s.dashboardStartAll)
	mux.HandleFunc("POST /api/dashboard/stop-all", s.dashboardStopAll)
	mux.HandleFunc("GET /api/dashboard/metrics", s.dashboardMetrics)
	mux.HandleFunc("GET /api/dashboard/configuration", s.dashboardConfiguration)
	mux.HandleFunc("GET /api/dashboard/logs", s.dashboardLogs)
	mux.HandleFunc("DELETE /api/dashboard/logs", s.dashboardClearLogs)
	mux.HandleFunc("POST /api/dashboard/models", s.dashboardCreateModel)
	mux.HandleFunc("PUT /api/dashboard/models/{model_id}", s.dashboardUpdateModel)
	mux.HandleFunc("DELETE /api/dashboard/models/{model_id}", s.dashboardDeleteModel)
	mux.HandleFunc("PUT /api/dashboard/judge-config", s.dashboardUpdateJudgeConfig)
	mux.HandleFunc("PUT /api/dashboard/routing-order", s.dashboardUpdateRoutingOrder)
	mux.HandleFunc("GET /api/dashboard/full-config", s.dashboardFullConfig)
	mux.HandleFunc("PUT /admin/config/keys", s.updateKeys)
	mux.HandleFunc("PATCH /admin/config/keys", s.updateKeys)
	mux.HandleFunc("POST /admin/config/test-key", s.testKey)
	mux.HandleFunc("GET /api/admin/policy", s.getPolicy)
	mux.HandleFunc("POST /api/admin/policy", s.updatePolicy)
	mux.HandleFunc("GET /api/admin/state", s.getAdminState)
	mux.HandleFunc("POST /api/admin/reset-cache", s.resetCache)
	mux.HandleFunc("POST /api/admin/reset-escalation", s.resetEscalation)
	mux.HandleFunc("GET /", s.dashboard)
	return s.cors(s.recover(mux))
}

func (s *Server) health(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "healthy", "service": "sentinelrouter"})
}

func (s *Server) models(w http.ResponseWriter, r *http.Request) {
	cfg := s.configManager.Current()
	data := make([]map[string]any, 0, len(cfg.Models))
	for id, model := range cfg.Models {
		if s.router.RuntimeFor(id, model).Status != "active" {
			continue
		}
		data = append(data, map[string]any{
			"id":       id,
			"object":   "model",
			"created":  0,
			"owned_by": "sentinelrouter",
			"root":     model.ModelID,
			"parent":   nil,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{"object": "list", "data": data})
}

func (s *Server) metricsSummary(w http.ResponseWriter, r *http.Request) {
	summary, err := s.store.MetricsSummary(r.Context(), strongModelSet(s.configManager.Current()))
	if err != nil {
		writeError(w, http.StatusInternalServerError, "metrics_error", "Failed to load metrics.")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"requests_total":  summary.RequestsTotal,
		"sessions_total":  summary.SessionsTotal,
		"cost_total":      summary.CostTotal,
		"escalation_rate": summary.EscalationRate,
		"strong_requests": summary.StrongRequests,
		"weak_requests":   summary.WeakRequests,
	})
}

func (s *Server) session(w http.ResponseWriter, r *http.Request) {
	sessionID := r.PathValue("session_id")
	session, found, err := s.store.GetSession(r.Context(), sessionID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "session_error", "Failed to load session.")
		return
	}
	if !found {
		writeError(w, http.StatusNotFound, "not_found", "Session not found")
		return
	}
	decisions, err := s.store.RoutingDecisionsBySession(r.Context(), sessionID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "session_error", "Failed to load decisions.")
		return
	}
	strongSet := strongModelSet(s.configManager.Current())
	strong := 0
	for _, d := range decisions {
		if strongSet[d.ModelUsed] {
			strong++
		}
	}
	rate := 0.0
	if len(decisions) > 0 {
		rate = float64(strong) / float64(len(decisions))
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"session_id":           session.SessionID,
		"client_ip":            nullString(session.ClientIP),
		"created_at":           session.CreatedAt.Format(time.RFC3339),
		"max_cost_per_session": session.MaxCostPerSession,
		"current_cost":         session.CurrentCost,
		"is_active":            session.IsActive,
		"total_requests":       len(decisions),
		"strong_requests":      strong,
		"weak_requests":        len(decisions) - strong,
		"escalation_rate":      rate,
	})
}

func (s *Server) audit(w http.ResponseWriter, r *http.Request) {
	sessionID := r.PathValue("session_id")
	decisions, err := s.store.RoutingDecisionsBySession(r.Context(), sessionID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "audit_error", "Failed to load audit.")
		return
	}
	if len(decisions) == 0 {
		writeError(w, http.StatusNotFound, "not_found", "No decisions found for this session")
		return
	}
	out := make([]map[string]any, 0, len(decisions))
	for _, d := range decisions {
		out = append(out, map[string]any{
			"request_id":       d.RequestID,
			"timestamp":        d.Timestamp.Format(time.RFC3339),
			"model_used":       d.ModelUsed,
			"complexity_score": d.ComplexityScore,
			"cost_incurred":    d.CostIncurred,
			"impact_scope":     nullString(d.ImpactScope),
			"reason":           nullString(d.Reason),
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{"session_id": sessionID, "decisions": out})
}

type chatRequest struct {
	Model       string             `json:"model"`
	Messages    []provider.Message `json:"messages"`
	Temperature *float64           `json:"temperature"`
	MaxTokens   *int               `json:"max_tokens"`
	Stream      bool               `json:"stream"`
	SessionID   string             `json:"session_id"`
	Tier        *string            `json:"tier"`
	UseJudge    *bool              `json:"use_judge"`
}

func (s *Server) chatCompletions(w http.ResponseWriter, r *http.Request) {
	var req chatRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_request", "Invalid JSON request.")
		return
	}
	if len(req.Messages) == 0 {
		writeError(w, http.StatusBadRequest, "invalid_request", "Messages array cannot be empty.")
		return
	}
	var prompt string
	for _, msg := range req.Messages {
		if msg.Content == "" {
			writeError(w, http.StatusBadRequest, "invalid_request", fmt.Sprintf("Message with role '%s' has null or missing content.", msg.Role))
			return
		}
		if msg.Role == "user" {
			prompt = msg.Content
		}
	}
	if prompt == "" {
		writeError(w, http.StatusBadRequest, "invalid_request", "No user message found in request.")
		return
	}
	defaults := s.currentDefaults()
	sessionID := firstNonEmpty(req.SessionID, r.Header.Get("X-Session-ID"))
	if sessionID == "" {
		if defaults.SessionIDStrategy == "ip_based" {
			host, _, _ := net.SplitHostPort(r.RemoteAddr)
			if host == "" {
				host = r.RemoteAddr
			}
			sum := sha256.Sum256([]byte(host))
			sessionID = "ip_" + host + "_" + hex.EncodeToString(sum[:4])
		} else if defaults.SessionIDStrategy == "uuid" {
			sessionID = router.NewID()
		} else {
			sessionID = defaults.DefaultSessionID
			if sessionID == "" {
				sessionID = router.NewID()
			}
		}
	}
	tier := defaults.DefaultTier
	if req.Tier != nil {
		tier = *req.Tier
	}
	useJudge := req.UseJudge
	if useJudge == nil {
		useJudge = defaults.DefaultUseJudge
	}
	opts := provider.Options{
		Temperature: req.Temperature,
		MaxTokens:   req.MaxTokens,
		Stream:      req.Stream,
	}
	if req.Stream {
		s.chatCompletionsStream(w, r, sessionID, tier, prompt, req.Messages, useJudge, opts)
		return
	}
	result, err := s.router.Route(r.Context(), sessionID, clientIP(r), tier, prompt, req.Messages, useJudge, opts, nil)
	if err != nil {
		status := http.StatusInternalServerError
		errorType := "internal_error"
		if strings.Contains(strings.ToLower(err.Error()), "budget exceeded") {
			status = http.StatusPaymentRequired
			errorType = "budget_exceeded"
		}
		writeError(w, status, errorType, err.Error())
		return
	}
	responseID := "chatcmpl-" + router.NewID()
	body := map[string]any{
		"id":      responseID,
		"object":  "chat.completion",
		"created": time.Now().Unix(),
		"model":   result.Response.Model,
		"choices": []map[string]any{{
			"index": 0,
			"message": map[string]any{
				"role":    "assistant",
				"content": result.Response.Content,
			},
			"finish_reason": "stop",
		}},
		"usage": map[string]int{
			"prompt_tokens":     result.Response.Usage.PromptTokens,
			"completion_tokens": result.Response.Usage.CompletionTokens,
			"total_tokens":      result.Response.Usage.TotalTokens,
		},
	}
	w.Header().Set("X-Sentinel-Model-Used", result.ModelUsed)
	w.Header().Set("X-Sentinel-Cost", fmt.Sprintf("%g", result.Cost))
	w.Header().Set("X-Sentinel-Session-Cost", fmt.Sprintf("%g", result.SessionCost))
	w.Header().Set("X-Sentinel-Complexity-Score", fmt.Sprintf("%g", result.ComplexityScore))
	w.Header().Set("X-Sentinel-Cycle-Detected", fmt.Sprintf("%t", result.CycleDetected))
	w.Header().Set("X-Sentinel-Session-ID", sessionID)
	writeJSON(w, http.StatusOK, body)
}

func (s *Server) chatCompletionsStream(w http.ResponseWriter, r *http.Request, sessionID, tier, prompt string, messages []provider.Message, useJudge *bool, opts provider.Options) {
	flusher, ok := w.(http.Flusher)
	if !ok {
		writeError(w, http.StatusInternalServerError, "internal_error", "Streaming not supported by server.")
		return
	}
	responseID := "chatcmpl-" + router.NewID()
	created := streamCreated()
	started := false
	startStream := func() {
		if started {
			return
		}
		setSSEHeaders(w)
		w.WriteHeader(http.StatusOK)
		started = true
	}

	var streamModel string
	result, err := s.router.Route(r.Context(), sessionID, clientIP(r), tier, prompt, messages, useJudge, opts, func(modelID string, chunk provider.StreamChunk) error {
		if modelID != "" {
			streamModel = modelID
		}
		if chunk.Content != "" {
			startStream()
			return writeSSEChunk(w, flusher, responseID, streamModel, created, chunk.Content)
		}
		if chunk.Done && chunk.Usage != nil {
			startStream()
			return writeSSEUsage(w, flusher, responseID, streamModel, created, *chunk.Usage)
		}
		return nil
	})
	if err != nil {
		if !started {
			status := http.StatusInternalServerError
			errorType := "internal_error"
			if strings.Contains(strings.ToLower(err.Error()), "budget exceeded") {
				status = http.StatusPaymentRequired
				errorType = "budget_exceeded"
			}
			writeError(w, status, errorType, err.Error())
			return
		}
		log.Printf("stream route error after headers sent: %v", err)
		return
	}
	if !started {
		startStream()
	}
	if streamModel == "" {
		streamModel = result.ModelUsed
	}
	w.Header().Set("X-Sentinel-Model-Used", result.ModelUsed)
	w.Header().Set("X-Sentinel-Cost", fmt.Sprintf("%g", result.Cost))
	w.Header().Set("X-Sentinel-Session-Cost", fmt.Sprintf("%g", result.SessionCost))
	w.Header().Set("X-Sentinel-Complexity-Score", fmt.Sprintf("%g", result.ComplexityScore))
	w.Header().Set("X-Sentinel-Cycle-Detected", fmt.Sprintf("%t", result.CycleDetected))
	w.Header().Set("X-Sentinel-Session-ID", sessionID)
	_ = writeSSEDone(w, flusher)
}

func (s *Server) getSessionDefaults(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"success": true, "data": s.currentDefaults()})
}

func (s *Server) updateSessionDefaults(w http.ResponseWriter, r *http.Request) {
	var updates map[string]json.RawMessage
	if err := json.NewDecoder(r.Body).Decode(&updates); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"success": false, "error": "Invalid JSON request."})
		return
	}
	s.mu.Lock()
	if raw, ok := updates["default_session_id"]; ok {
		_ = json.Unmarshal(raw, &s.sessionDefaults.DefaultSessionID)
	}
	if raw, ok := updates["default_tier"]; ok {
		_ = json.Unmarshal(raw, &s.sessionDefaults.DefaultTier)
	}
	if raw, ok := updates["default_use_judge"]; ok {
		if string(raw) == "null" {
			s.sessionDefaults.DefaultUseJudge = nil
		} else {
			var value bool
			if err := json.Unmarshal(raw, &value); err == nil {
				s.sessionDefaults.DefaultUseJudge = &value
			}
		}
	}
	if raw, ok := updates["session_id_strategy"]; ok {
		_ = json.Unmarshal(raw, &s.sessionDefaults.SessionIDStrategy)
	}
	defaults := s.sessionDefaults
	s.mu.Unlock()
	if err := s.store.SaveState(r.Context(), sessionDefaultsStateKey, defaults); err != nil {
		writeError(w, http.StatusInternalServerError, "state_persist_error", "Failed to persist session defaults.")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"success": true, "message": "Session defaults updated successfully", "data": defaults})
}

func (s *Server) regenerateSessionID(w http.ResponseWriter, r *http.Request) {
	s.mu.Lock()
	s.sessionDefaults.DefaultSessionID = router.NewID()
	defaults := s.sessionDefaults
	s.mu.Unlock()
	if err := s.store.SaveState(r.Context(), sessionDefaultsStateKey, defaults); err != nil {
		writeError(w, http.StatusInternalServerError, "state_persist_error", "Failed to persist session defaults.")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"success": true, "message": "Session ID regenerated successfully", "data": map[string]string{"default_session_id": defaults.DefaultSessionID}})
}

func (s *Server) dashboardLive(w http.ResponseWriter, r *http.Request) {
	cfg := s.configManager.Current()
	models := make([]map[string]any, 0, len(cfg.Models))
	for id, model := range cfg.Models {
		runtime := s.router.RuntimeFor(id, model)
		models = append(models, map[string]any{
			"id":     id,
			"config": s.dashboardModelConfig(id, model),
			"state": map[string]any{
				"current_rpm":        runtime.CurrentRPM,
				"requests_today":     runtime.RequestsToday,
				"tokens_today":       runtime.TokensToday,
				"total_cost_session": runtime.TotalCostSession,
				"last_updated_ts":    runtime.LastUpdated,
				"exhausted_until_ts": nil,
			},
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{"models": models})
}

func (s *Server) dashboardResetModelCost(w http.ResponseWriter, r *http.Request) {
	s.router.ResetModelCost(r.PathValue("model_id"))
	writeJSON(w, http.StatusOK, map[string]any{"status": "success", "message": fmt.Sprintf("Cost reset for %s", r.PathValue("model_id"))})
}

func (s *Server) dashboardModelStatus(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Status string `json:"status"`
	}
	_ = json.NewDecoder(r.Body).Decode(&req)
	status := strings.ToLower(req.Status)
	if status != "active" && status != "inactive" && status != "disabled" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"detail": "Invalid status"})
		return
	}
	modelID := r.PathValue("model_id")
	if _, ok := s.configManager.Current().Models[modelID]; !ok {
		writeJSON(w, http.StatusNotFound, map[string]any{"detail": fmt.Sprintf("model %s not found", modelID)})
		return
	}
	s.router.SetModelStatus(modelID, status)
	writeJSON(w, http.StatusOK, map[string]any{"status": "success", "message": fmt.Sprintf("Model %s status set to %s", modelID, status)})
}

func (s *Server) dashboardResetAllCosts(w http.ResponseWriter, r *http.Request) {
	s.router.ResetAllModelCosts(s.configManager.Current())
	writeJSON(w, http.StatusOK, map[string]any{"status": "success", "message": "All costs reset"})
}

func (s *Server) dashboardStartAll(w http.ResponseWriter, r *http.Request) {
	s.router.SetAllModelStatus(s.configManager.Current(), "active")
	writeJSON(w, http.StatusOK, map[string]any{"status": "success", "message": "All models activated"})
}

func (s *Server) dashboardStopAll(w http.ResponseWriter, r *http.Request) {
	s.router.SetAllModelStatus(s.configManager.Current(), "disabled")
	writeJSON(w, http.StatusOK, map[string]any{"status": "success", "message": "All models stopped"})
}

func (s *Server) dashboardMetrics(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, s.metrics.DashboardAggregate(10000))
}

func (s *Server) dashboardConfiguration(w http.ResponseWriter, r *http.Request) {
	cfg := s.configManager.Current()
	apiKeys := map[string]string{}
	apiKeyTypes := map[string]string{}
	for id, key := range cfg.Keys {
		apiKeys[id] = key.Value
		apiKeyTypes[id] = string(key.Type)
	}
	models := make([]map[string]any, 0, len(cfg.Models))
	for id, model := range cfg.Models {
		models = append(models, map[string]any{"id": id, "config": s.dashboardModelConfig(id, model)})
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"api_keys":        apiKeys,
		"api_key_types":   apiKeyTypes,
		"models":          models,
		"system_settings": s.currentDefaults(),
	})
}

func (s *Server) dashboardLogs(w http.ResponseWriter, r *http.Request) {
	limit := 50
	decisions, err := s.store.RecentRoutingDecisions(r.Context(), limit)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"detail": err.Error()})
		return
	}
	logs := make([]map[string]any, 0, len(decisions))
	for _, d := range decisions {
		logs = append(logs, map[string]any{
			"session_id":         d.SessionID,
			"request_id":         d.RequestID,
			"model_used":         d.ModelUsed,
			"complexity_score":   d.ComplexityScore,
			"cost_incurred":      d.CostIncurred,
			"cost_source":        d.CostSource,
			"computed_cost":      nullFloat(d.ComputedCost),
			"impact_scope":       nullString(d.ImpactScope),
			"reason":             nullString(d.Reason),
			"timestamp":          d.Timestamp.Unix(),
			"decision_reason":    nullString(d.Reason),
			"cycle_detected":     strings.Contains(strings.ToLower(d.Reason.String), "cycle"),
			"request_latency_ms": d.RequestLatencyMS,
			"model_latency_ms":   d.ModelLatencyMS,
			"judge_latency_ms":   nullFloat(d.JudgeLatencyMS),
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{"logs": logs})
}

func (s *Server) dashboardClearLogs(w http.ResponseWriter, r *http.Request) {
	if err := s.store.ClearRoutingDecisions(r.Context()); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"detail": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "success", "message": "All logs cleared"})
}

func (s *Server) dashboardCreateModel(w http.ResponseWriter, r *http.Request) {
	var req struct {
		ModelID string         `json:"model_id"`
		Config  map[string]any `json:"config"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil || req.ModelID == "" || req.Config == nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"detail": "model_id and config are required"})
		return
	}
	if err := s.patchRawConfig(func(raw map[string]any) error {
		models, _ := raw["models"].(map[string]any)
		if models == nil {
			models = map[string]any{}
			raw["models"] = models
		}
		if _, exists := models[req.ModelID]; exists {
			return fmt.Errorf("model %s already exists", req.ModelID)
		}
		models[req.ModelID] = req.Config
		return nil
	}); err != nil {
		writeJSON(w, http.StatusConflict, map[string]any{"detail": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "success", "message": fmt.Sprintf("Model %s created", req.ModelID), "model_id": req.ModelID})
}

func (s *Server) dashboardUpdateModel(w http.ResponseWriter, r *http.Request) {
	var updates map[string]any
	if err := json.NewDecoder(r.Body).Decode(&updates); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"detail": "Invalid JSON request."})
		return
	}
	modelID := r.PathValue("model_id")
	if err := s.patchRawConfig(func(raw map[string]any) error {
		models, _ := raw["models"].(map[string]any)
		model, _ := models[modelID].(map[string]any)
		if model == nil {
			return fmt.Errorf("model %s not found", modelID)
		}
		for k, v := range updates {
			model[k] = v
		}
		return nil
	}); err != nil {
		writeJSON(w, http.StatusNotFound, map[string]any{"detail": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "success", "message": fmt.Sprintf("Model %s updated", modelID)})
}

func (s *Server) dashboardDeleteModel(w http.ResponseWriter, r *http.Request) {
	modelID := r.PathValue("model_id")
	if err := s.patchRawConfig(func(raw map[string]any) error {
		models, _ := raw["models"].(map[string]any)
		if _, ok := models[modelID]; !ok {
			return fmt.Errorf("model %s not found", modelID)
		}
		delete(models, modelID)
		return nil
	}); err != nil {
		writeJSON(w, http.StatusNotFound, map[string]any{"detail": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "success", "message": fmt.Sprintf("Model %s deleted", modelID)})
}

func (s *Server) dashboardUpdateJudgeConfig(w http.ResponseWriter, r *http.Request) {
	var updates map[string]any
	if err := json.NewDecoder(r.Body).Decode(&updates); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"detail": "Invalid JSON request."})
		return
	}
	if err := s.patchRawConfig(func(raw map[string]any) error {
		judge, _ := raw["judge"].(map[string]any)
		if judge == nil {
			judge = map[string]any{}
			raw["judge"] = judge
		}
		for k, v := range updates {
			judge[k] = v
		}
		return nil
	}); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"detail": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "success", "message": "Judge config updated", "config": s.configManager.Current().Judge})
}

func (s *Server) dashboardUpdateRoutingOrder(w http.ResponseWriter, r *http.Request) {
	var updates map[string]any
	if err := json.NewDecoder(r.Body).Decode(&updates); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"detail": "Invalid JSON request."})
		return
	}
	if err := s.patchRawConfig(func(raw map[string]any) error {
		policy, _ := raw["routing_policy"].(map[string]any)
		if policy == nil {
			policy = map[string]any{}
			raw["routing_policy"] = policy
		}
		for k, v := range updates {
			policy[k] = v
		}
		return nil
	}); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"detail": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "success", "message": "Routing order config updated", "config": s.configManager.Current().RoutingPolicy})
}

func (s *Server) dashboardFullConfig(w http.ResponseWriter, r *http.Request) {
	cfg := s.configManager.Current()
	writeJSON(w, http.StatusOK, map[string]any{
		"system_settings":      s.currentDefaults(),
		"models":               cfg.Models,
		"judge_config":         cfg.Judge,
		"routing_order_config": cfg.RoutingPolicy,
	})
}

func (s *Server) dashboardModelConfig(modelID string, model config.ModelDefinition) map[string]any {
	data := map[string]any{}
	encoded, err := json.Marshal(model)
	if err == nil {
		_ = json.Unmarshal(encoded, &data)
	}
	if data["display_name"] == nil || data["display_name"] == "" {
		data["display_name"] = modelID
	}
	runtime := s.router.RuntimeFor(modelID, model)
	data["status"] = runtime.Status
	priorityGroup, order := s.routingPlacement(modelID)
	data["routing"] = map[string]any{
		"priority_group": priorityGroup,
		"order":          order,
	}
	return data
}

func (s *Server) routingPlacement(modelID string) (string, int) {
	cfg := s.configManager.Current()
	for index, id := range cfg.RoutingPolicy.WeakTier.Order {
		if id == modelID {
			return "fast_tier", index + 1
		}
	}
	for index, id := range cfg.RoutingPolicy.StrongTier.Order {
		if id == modelID {
			return "strong_tier", index + 1
		}
	}
	return "unassigned", 0
}

type keysUpdate struct {
	Keys map[string]struct {
		Value string `json:"value"`
		Type  string `json:"type"`
	} `json:"keys"`
}

func (s *Server) updateKeys(w http.ResponseWriter, r *http.Request) {
	if !s.authorized(r) {
		writeJSON(w, http.StatusUnauthorized, map[string]any{"detail": "Unauthorized"})
		return
	}
	var req keysUpdate
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"detail": "Invalid JSON request."})
		return
	}
	raw, err := s.ensureRawSentinelConfig()
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"detail": err.Error()})
		return
	}
	keys, _ := raw["keys"].(map[string]any)
	if keys == nil {
		keys = map[string]any{}
		raw["keys"] = keys
	}
	updated := make([]string, 0, len(req.Keys))
	masked := map[string]string{}
	for keyID, update := range req.Keys {
		value := strings.TrimSpace(update.Value)
		if value == "" || strings.ContainsAny(value, " \n\r\t") || (len(value) < 8 && !isEnvPlaceholder(value)) {
			writeJSON(w, http.StatusBadRequest, map[string]any{"detail": "Key value must be at least 8 characters or an env placeholder and must not contain whitespace"})
			return
		}
		existing, exists := keys[keyID].(map[string]any)
		if exists {
			existing["value"] = value
		} else {
			if update.Type == "" {
				writeJSON(w, http.StatusBadRequest, map[string]any{"detail": fmt.Sprintf("Key '%s' requires provider type for creation", keyID)})
				return
			}
			keys[keyID] = map[string]any{"type": strings.ToLower(update.Type), "value": value}
		}
		updated = append(updated, keyID)
		masked[keyID] = maskKey(value)
	}
	if err := writeJSONFileAtomic(s.settings.SentinelConfigPath, raw); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"detail": err.Error()})
		return
	}
	if err := s.configManager.ForceReload(); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"detail": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"success": true, "message": "Keys updated successfully", "updated_keys": updated, "masked_updates": masked})
}

type keyTestRequest struct {
	KeyID          string   `json:"key_id"`
	Value          string   `json:"value"`
	Provider       string   `json:"provider"`
	TimeoutSeconds *float64 `json:"timeout_seconds"`
}

func (s *Server) testKey(w http.ResponseWriter, r *http.Request) {
	if !s.authorized(r) {
		writeJSON(w, http.StatusUnauthorized, map[string]any{"valid": false, "message": "Unauthorized"})
		return
	}
	var req keyTestRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusUnprocessableEntity, map[string]any{"valid": false, "message": "Invalid request payload."})
		return
	}
	providerType := config.ProviderType(strings.ToLower(req.Provider))
	if providerType == "" && req.KeyID != "" {
		if key, ok := s.configManager.Current().Keys[req.KeyID]; ok {
			providerType = key.Type
		}
	}
	if providerType == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"valid": false, "message": "Provider type required for key validation."})
		return
	}
	timeout := 10 * time.Second
	if req.TimeoutSeconds != nil {
		timeout = time.Duration(*req.TimeoutSeconds * float64(time.Second))
	}
	valid, message := provider.ValidateProviderKey(r.Context(), providerType, req.Value, timeout)
	writeJSON(w, http.StatusOK, map[string]any{"valid": valid, "message": message})
}

func (s *Server) getPolicy(w http.ResponseWriter, r *http.Request) {
	defaults := s.currentDefaults()
	writeJSON(w, http.StatusOK, map[string]any{
		"success": true,
		"data": map[string]any{
			"budget_control": map[string]any{
				"max_cost_per_session":  s.settings.MaxCostPerSession,
				"escalation_rate_limit": s.settings.EscalationRateLimit,
				"rolling_window_size":   s.settings.RollingWindowSize,
			},
			"judge": map[string]any{
				"enabled":              defaults.DefaultUseJudge == nil || *defaults.DefaultUseJudge,
				"mode":                 judgeMode(defaults.DefaultUseJudge),
				"complexity_threshold": s.settings.ComplexityThreshold,
			},
			"semantic_cache": map[string]any{
				"enabled":              s.settings.SemanticCacheEnabled,
				"min_samples":          s.settings.SemanticCacheMinSamples,
				"confidence_threshold": s.settings.SemanticCacheConfidence,
				"ttl_seconds":          s.settings.SemanticCacheTTLSeconds,
			},
			"cycle_detection": map[string]any{
				"enabled":                    s.settings.EnableCycleDetection,
				"window_size":                s.settings.CycleDetectionWindowSize,
				"simhash_distance_threshold": s.settings.CycleDetectionThreshold,
			},
		},
	})
}

func (s *Server) updatePolicy(w http.ResponseWriter, r *http.Request) {
	var updates map[string]any
	if err := json.NewDecoder(r.Body).Decode(&updates); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"success": false, "error": "Invalid JSON request."})
		return
	}
	warnings := []string{}
	if budgetControl, ok := updates["budget_control"].(map[string]any); ok {
		if value, ok := numberValue(budgetControl["max_cost_per_session"]); ok {
			s.settings.MaxCostPerSession = value
			warnings = append(warnings, "max_cost_per_session changed - may immediately block in-flight sessions")
		}
		if value, ok := numberValue(budgetControl["escalation_rate_limit"]); ok {
			s.settings.EscalationRateLimit = value
			s.settings.TargetEscalationRate = value
		}
		if value, ok := numberValue(budgetControl["rolling_window_size"]); ok {
			s.settings.RollingWindowSize = int(value)
			warnings = append(warnings, "rolling_window_size changed - escalation counters were reset")
		}
	}
	if judgePolicy, ok := updates["judge"].(map[string]any); ok {
		if mode, ok := judgePolicy["mode"].(string); ok {
			s.mu.Lock()
			switch mode {
			case "always":
				value := true
				s.sessionDefaults.DefaultUseJudge = &value
			case "never":
				value := false
				s.sessionDefaults.DefaultUseJudge = &value
			case "smart":
				s.sessionDefaults.DefaultUseJudge = nil
			}
			s.mu.Unlock()
		}
		if value, ok := numberValue(judgePolicy["complexity_threshold"]); ok {
			s.settings.ComplexityThreshold = value
		}
	}
	if semanticPolicy, ok := updates["semantic_cache"].(map[string]any); ok {
		if enabled, ok := semanticPolicy["enabled"].(bool); ok {
			s.settings.SemanticCacheEnabled = enabled
		}
		if value, ok := numberValue(semanticPolicy["min_samples"]); ok {
			s.settings.SemanticCacheMinSamples = int(value)
			warnings = append(warnings, "semantic_cache.min_samples changed - semantic cache was reset")
		}
		if value, ok := numberValue(semanticPolicy["confidence_threshold"]); ok {
			s.settings.SemanticCacheConfidence = value
		}
		if value, ok := numberValue(semanticPolicy["ttl_seconds"]); ok {
			s.settings.SemanticCacheTTLSeconds = int(value)
		}
	}
	if cyclePolicy, ok := updates["cycle_detection"].(map[string]any); ok {
		if enabled, ok := cyclePolicy["enabled"].(bool); ok {
			s.settings.EnableCycleDetection = enabled
		}
		if value, ok := numberValue(cyclePolicy["window_size"]); ok {
			s.settings.CycleDetectionWindowSize = int(value)
			warnings = append(warnings, "cycle_detection.window_size changed - cycle detector state was reset")
		}
		if value, ok := numberValue(cyclePolicy["simhash_distance_threshold"]); ok {
			s.settings.CycleDetectionThreshold = int(value)
			warnings = append(warnings, "cycle_detection.simhash_distance_threshold changed - cycle detector state was reset")
		}
	}
	s.router.UpdatePolicy(s.settings)
	if err := s.store.SaveState(r.Context(), adminPolicyStateKey, s.persistedPolicy()); err != nil {
		warnings = append(warnings, "admin policy changed but could not be persisted: "+err.Error())
	}
	if err := s.store.SaveState(r.Context(), sessionDefaultsStateKey, s.currentDefaults()); err != nil {
		warnings = append(warnings, "session defaults changed but could not be persisted: "+err.Error())
	}
	writeJSON(w, http.StatusOK, map[string]any{"success": true, "message": "Admin policy updated successfully", "warnings": warnings, "data": updates})
}

func (s *Server) getAdminState(w http.ResponseWriter, r *http.Request) {
	cfg := s.configManager.Current()
	weak := cfg.RoutingPolicy.WeakTier.Order
	strong := cfg.RoutingPolicy.StrongTier.Order
	summary, _ := s.store.MetricsSummary(r.Context(), strongModelSet(cfg))
	dashboardMetrics := s.metrics.DashboardAggregate(10000)
	cacheHits, cacheMisses, cacheClusters, _ := s.store.SemanticCacheSummary(r.Context())
	cacheTotal := cacheHits + cacheMisses
	cacheHitRate := 0.0
	if cacheTotal > 0 {
		cacheHitRate = float64(cacheHits) / float64(cacheTotal)
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"success": true,
		"data": map[string]any{
			"routing": map[string]any{
				"weak_models":   weak,
				"strong_models": strong,
				"routing_order": append(append([]string{}, weak...), strong...),
			},
			"judge": map[string]any{
				"invoked_count":  dashboardMetrics.JudgeCallCount,
				"skipped_count":  dashboardMetrics.JudgeSkipCount,
				"skip_rate":      dashboardMetrics.JudgeSkipRate,
				"success_rate":   dashboardMetrics.JudgeSuccessRate,
				"avg_latency_ms": dashboardMetrics.JudgeLatency.AvgMS,
				"registry":       s.router.JudgeRegistryStatus(),
			},
			"semantic_cache": map[string]any{"hit_count": cacheHits, "miss_count": cacheMisses, "hit_rate": cacheHitRate, "active_clusters": cacheClusters, "judge_skip_attribution": dashboardMetrics.JudgeBreakdown["semantic_cache"]},
			"escalation":     map[string]any{"current_rate": summary.EscalationRate, "target_rate": s.settings.TargetEscalationRate, "is_strict_mode": summary.EscalationRate > s.settings.TargetEscalationRate, "effective_threshold": s.settings.InitialThreshold},
		},
	})
}

func (s *Server) resetCache(w http.ResponseWriter, r *http.Request) {
	s.router.ResetSemanticCache()
	writeJSON(w, http.StatusOK, map[string]any{"success": true, "message": "Semantic cache reset successfully"})
}

func (s *Server) resetEscalation(w http.ResponseWriter, r *http.Request) {
	s.router.ResetEscalation()
	writeJSON(w, http.StatusOK, map[string]any{"success": true, "message": "Escalation counters reset successfully"})
}

func (s *Server) dashboard(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" {
		http.NotFound(w, r)
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	_, _ = w.Write([]byte(dashboardHTML))
}

func (s *Server) currentDefaults() SessionDefaults {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.sessionDefaults
}

func loadPersistedRuntimeState(store *storage.Store, settings config.Settings, defaults SessionDefaults) (config.Settings, SessionDefaults) {
	if store == nil {
		return settings, defaults
	}
	ctx := contextWithTimeout()
	defer ctx.cancel()
	var policy persistedPolicy
	if ok, err := store.LoadState(ctx.context, adminPolicyStateKey, &policy); err == nil && ok {
		settings = applyPersistedPolicy(settings, policy)
	} else if err != nil {
		log.Printf("failed to load persisted admin policy: %v", err)
	}
	var persistedDefaults SessionDefaults
	if ok, err := store.LoadState(ctx.context, sessionDefaultsStateKey, &persistedDefaults); err == nil && ok {
		defaults = persistedDefaults
	} else if err != nil {
		log.Printf("failed to load persisted session defaults: %v", err)
	}
	return settings, defaults
}

func applyPersistedPolicy(settings config.Settings, policy persistedPolicy) config.Settings {
	settings.MaxCostPerSession = policy.MaxCostPerSession
	settings.EscalationRateLimit = policy.EscalationRateLimit
	settings.TargetEscalationRate = firstPositive(policy.TargetEscalationRate, policy.EscalationRateLimit)
	settings.RollingWindowSize = policy.RollingWindowSize
	settings.ComplexityThreshold = policy.ComplexityThreshold
	settings.SemanticCacheEnabled = policy.SemanticCacheEnabled
	settings.SemanticCacheMinSamples = policy.SemanticCacheMinSamples
	settings.SemanticCacheConfidence = policy.SemanticCacheConfidence
	settings.SemanticCacheTTLSeconds = policy.SemanticCacheTTLSeconds
	settings.EnableCycleDetection = policy.EnableCycleDetection
	settings.CycleDetectionWindowSize = policy.CycleDetectionWindowSize
	settings.CycleDetectionThreshold = policy.CycleDetectionThreshold
	return settings
}

func (s *Server) persistedPolicy() persistedPolicy {
	return persistedPolicy{
		MaxCostPerSession:        s.settings.MaxCostPerSession,
		EscalationRateLimit:      s.settings.EscalationRateLimit,
		TargetEscalationRate:     s.settings.TargetEscalationRate,
		RollingWindowSize:        s.settings.RollingWindowSize,
		ComplexityThreshold:      s.settings.ComplexityThreshold,
		SemanticCacheEnabled:     s.settings.SemanticCacheEnabled,
		SemanticCacheMinSamples:  s.settings.SemanticCacheMinSamples,
		SemanticCacheConfidence:  s.settings.SemanticCacheConfidence,
		SemanticCacheTTLSeconds:  s.settings.SemanticCacheTTLSeconds,
		EnableCycleDetection:     s.settings.EnableCycleDetection,
		CycleDetectionWindowSize: s.settings.CycleDetectionWindowSize,
		CycleDetectionThreshold:  s.settings.CycleDetectionThreshold,
	}
}

type timeoutContext struct {
	context context.Context
	cancel  func()
}

func contextWithTimeout() timeoutContext {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	return timeoutContext{context: ctx, cancel: cancel}
}

func (s *Server) authorized(r *http.Request) bool {
	if s.settings.AdminAPIToken == "" {
		return false
	}
	token := r.Header.Get("X-Admin-Token")
	if token == "" {
		auth := r.Header.Get("Authorization")
		if strings.HasPrefix(strings.ToLower(auth), "bearer ") {
			token = strings.TrimSpace(auth[7:])
		}
	}
	if token == "" {
		return false
	}
	return subtle.ConstantTimeCompare([]byte(token), []byte(s.settings.AdminAPIToken)) == 1
}

func (s *Server) ensureRawSentinelConfig() (map[string]any, error) {
	if data, err := os.ReadFile(s.settings.SentinelConfigPath); err == nil {
		var raw map[string]any
		if err := json.Unmarshal(data, &raw); err != nil {
			return nil, err
		}
		return raw, nil
	}
	cfg := s.configManager.Current()
	data, err := json.Marshal(cfg)
	if err != nil {
		return nil, err
	}
	var raw map[string]any
	if err := json.Unmarshal(data, &raw); err != nil {
		return nil, err
	}
	return raw, nil
}

func (s *Server) patchRawConfig(mutator func(map[string]any) error) error {
	raw, err := s.ensureRawSentinelConfig()
	if err != nil {
		return err
	}
	if err := mutator(raw); err != nil {
		return err
	}
	data, err := json.Marshal(raw)
	if err != nil {
		return err
	}
	var candidate config.SentinelConfig
	if err := json.Unmarshal(data, &candidate); err != nil {
		return err
	}
	if err := candidate.Validate(); err != nil {
		return err
	}
	if err := writeJSONFileAtomic(s.settings.SentinelConfigPath, raw); err != nil {
		return err
	}
	return s.configManager.ForceReload()
}

func (s *Server) setAllModelsEnabled(enabled bool) error {
	return s.patchRawConfig(func(raw map[string]any) error {
		models, _ := raw["models"].(map[string]any)
		for _, value := range models {
			if model, ok := value.(map[string]any); ok {
				model["enabled"] = enabled
			}
		}
		return nil
	})
}

func (s *Server) cors(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if s.settings.CORSOrigins == "*" {
			w.Header().Set("Access-Control-Allow-Origin", "*")
		} else {
			origin := r.Header.Get("Origin")
			for _, allowed := range strings.Split(s.settings.CORSOrigins, ",") {
				if strings.TrimSpace(allowed) == origin {
					w.Header().Set("Access-Control-Allow-Origin", origin)
					break
				}
			}
		}
		w.Header().Set("Access-Control-Allow-Methods", "GET,POST,PUT,PATCH,DELETE,OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Authorization,Content-Type,X-Admin-Token,X-Session-ID")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func (s *Server) recover(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			if recovered := recover(); recovered != nil {
				log.Printf("panic serving %s: %v", r.URL.Path, recovered)
				writeError(w, http.StatusInternalServerError, "internal_error", "Internal server error")
			}
		}()
		next.ServeHTTP(w, r)
	})
}

func strongModelSet(cfg *config.SentinelConfig) map[string]bool {
	out := map[string]bool{}
	if cfg == nil {
		return out
	}
	for _, modelID := range cfg.RoutingPolicy.StrongTier.Order {
		out[modelID] = true
	}
	return out
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

func writeError(w http.ResponseWriter, status int, errorType, message string) {
	writeJSON(w, status, map[string]any{"error": map[string]any{"message": message, "type": errorType, "code": status}})
}

func writeJSONFileAtomic(path string, value any) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	data = append(data, '\n')
	tmp, err := os.CreateTemp(filepath.Dir(path), ".tmp-")
	if err != nil {
		return err
	}
	tmpName := tmp.Name()
	if _, err := tmp.Write(data); err != nil {
		_ = tmp.Close()
		_ = os.Remove(tmpName)
		return err
	}
	if err := tmp.Sync(); err != nil {
		_ = tmp.Close()
		_ = os.Remove(tmpName)
		return err
	}
	if err := tmp.Close(); err != nil {
		_ = os.Remove(tmpName)
		return err
	}
	return os.Rename(tmpName, path)
}

func nullString(value sql.NullString) any {
	if value.Valid {
		return value.String
	}
	return nil
}

func nullFloat(value sql.NullFloat64) any {
	if value.Valid {
		return value.Float64
	}
	return nil
}

func numberValue(value any) (float64, bool) {
	switch v := value.(type) {
	case float64:
		return v, true
	case int:
		return float64(v), true
	case json.Number:
		parsed, err := v.Float64()
		return parsed, err == nil
	default:
		return 0, false
	}
}

func isEnvPlaceholder(value string) bool {
	return strings.HasPrefix(value, "${") && strings.HasSuffix(value, "}") && len(value) > 3
}

func clientIP(r *http.Request) string {
	if forwarded := r.Header.Get("X-Forwarded-For"); forwarded != "" {
		return strings.TrimSpace(strings.Split(forwarded, ",")[0])
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return host
}

func firstPositive(values ...float64) float64 {
	for _, value := range values {
		if value > 0 {
			return value
		}
	}
	return 0
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if value != "" {
			return value
		}
	}
	return ""
}

func maskKey(value string) string {
	if value == "" {
		return "Not set"
	}
	if len(value) <= 8 {
		return "****"
	}
	return value[:4] + "..." + value[len(value)-4:]
}

func judgeMode(value *bool) string {
	if value == nil {
		return "smart"
	}
	if *value {
		return "always"
	}
	return "never"
}
