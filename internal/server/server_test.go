package server

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/ShonT/LLMSentinelRouter/internal/config"
	"github.com/ShonT/LLMSentinelRouter/internal/metrics"
	"github.com/ShonT/LLMSentinelRouter/internal/storage"
)

func TestServerE2EChatMetricsSessionAndAudit(t *testing.T) {
	fakeProvider := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/chat/completions":
			var payload map[string]any
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				t.Fatalf("decode provider request: %v", err)
			}
			if payload["model"] != "fake-weak-model" {
				t.Fatalf("provider model = %v, want fake-weak-model", payload["model"])
			}
			writeJSON(w, http.StatusOK, map[string]any{
				"choices": []map[string]any{{
					"message": map[string]any{"content": "weak response"},
				}},
				"usage": map[string]int{"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
			})
		case "/models":
			writeJSON(w, http.StatusOK, map[string]any{"data": []map[string]string{{"id": "fake-weak-model"}}})
		default:
			t.Fatalf("unexpected provider path %s", r.URL.Path)
		}
	}))
	defer fakeProvider.Close()
	t.Setenv("DEEPSEEK_BASE_URL", fakeProvider.URL)

	app := newTestServer(t)
	body := `{"messages":[{"role":"user","content":"hello"}],"session_id":"session-e2e","tier":"paid","use_judge":false}`
	rr := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	app.Handler().ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("chat status = %d body=%s", rr.Code, rr.Body.String())
	}
	if got := rr.Header().Get("X-Sentinel-Model-Used"); got != "weak-deepseek" {
		t.Fatalf("model header = %q, want weak-deepseek", got)
	}
	var chat map[string]any
	if err := json.Unmarshal(rr.Body.Bytes(), &chat); err != nil {
		t.Fatalf("decode chat response: %v", err)
	}
	choices := chat["choices"].([]any)
	message := choices[0].(map[string]any)["message"].(map[string]any)
	if message["content"] != "weak response" {
		t.Fatalf("content = %v", message["content"])
	}

	assertGET(t, app, "/metrics", http.StatusOK, func(payload map[string]any) {
		if payload["requests_total"].(float64) != 1 {
			t.Fatalf("requests_total = %v", payload["requests_total"])
		}
	})
	assertGET(t, app, "/sessions/session-e2e", http.StatusOK, func(payload map[string]any) {
		if payload["total_requests"].(float64) != 1 {
			t.Fatalf("total_requests = %v", payload["total_requests"])
		}
	})
	assertGET(t, app, "/audit/session-e2e", http.StatusOK, func(payload map[string]any) {
		decisions := payload["decisions"].([]any)
		if len(decisions) != 1 {
			t.Fatalf("decisions len = %d", len(decisions))
		}
	})
}

func TestAdminKeyValidationUsesProviderCheck(t *testing.T) {
	fakeProvider := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/models" {
			t.Fatalf("unexpected provider path %s", r.URL.Path)
		}
		if got := r.Header.Get("Authorization"); got != "Bearer valid-key-123" {
			t.Fatalf("authorization = %q", got)
		}
		writeJSON(w, http.StatusOK, map[string]any{"data": []map[string]string{{"id": "fake"}}})
	}))
	defer fakeProvider.Close()
	t.Setenv("DEEPSEEK_BASE_URL", fakeProvider.URL)

	app := newTestServer(t)
	reqBody := `{"provider":"deepseek","value":"valid-key-123"}`
	req := httptest.NewRequest(http.MethodPost, "/admin/config/test-key", strings.NewReader(reqBody))
	req.Header.Set("X-Admin-Token", "admin-token")
	rr := httptest.NewRecorder()
	app.Handler().ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("status = %d body=%s", rr.Code, rr.Body.String())
	}
	var payload map[string]any
	if err := json.Unmarshal(rr.Body.Bytes(), &payload); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if payload["valid"] != true {
		t.Fatalf("valid = %v", payload["valid"])
	}
}

func TestConditionalJudgeTimeoutEscalatesToStrongModel(t *testing.T) {
	fakeProvider := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/chat/completions":
			time.Sleep(50 * time.Millisecond)
			writeJSON(w, http.StatusOK, map[string]any{
				"choices": []map[string]any{{"message": map[string]any{"content": "late weak response"}}},
				"usage":   map[string]int{"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
			})
		case "/v1/messages":
			writeJSON(w, http.StatusOK, map[string]any{
				"content": []map[string]string{{"text": "strong response"}},
				"usage":   map[string]int{"input_tokens": 20, "output_tokens": 8},
			})
		default:
			t.Fatalf("unexpected provider path %s", r.URL.Path)
		}
	}))
	defer fakeProvider.Close()
	t.Setenv("DEEPSEEK_BASE_URL", fakeProvider.URL)
	t.Setenv("ANTHROPIC_BASE_URL", fakeProvider.URL)

	app := newTestServer(t)
	app.settings.ConditionalJudgeTimeout = 0.01
	app.router.UpdatePolicy(app.settings)
	prompt := strings.Repeat("production security deploy database migration ", 20)
	body := `{"messages":[{"role":"user","content":"` + prompt + `"}],"session_id":"session-timeout"}`
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	app.Handler().ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("chat status = %d body=%s", rr.Code, rr.Body.String())
	}
	if got := rr.Header().Get("X-Sentinel-Model-Used"); got != "strong-anthropic" {
		t.Fatalf("model header = %q, want strong-anthropic", got)
	}
	if !strings.Contains(rr.Body.String(), "strong response") {
		t.Fatalf("body does not contain strong response: %s", rr.Body.String())
	}
}

func TestDashboardAndAdminConfigFlows(t *testing.T) {
	app := newTestServer(t)

	rr := httptest.NewRecorder()
	app.Handler().ServeHTTP(rr, httptest.NewRequest(http.MethodGet, "/", nil))
	if rr.Code != http.StatusOK || !strings.Contains(rr.Body.String(), "SentinelRouter Enhanced Dashboard") {
		t.Fatalf("dashboard root status=%d body prefix=%q", rr.Code, rr.Body.String()[:min(len(rr.Body.String()), 80)])
	}

	assertGET(t, app, "/v1/models", http.StatusOK, func(payload map[string]any) {
		models := payload["data"].([]any)
		if len(models) != 2 {
			t.Fatalf("models len = %d", len(models))
		}
	})

	req := httptest.NewRequest(http.MethodPost, "/api/dashboard/model/weak-deepseek/status", strings.NewReader(`{"status":"disabled"}`))
	rr = httptest.NewRecorder()
	app.Handler().ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("model status update = %d body=%s", rr.Code, rr.Body.String())
	}
	assertGET(t, app, "/v1/models", http.StatusOK, func(payload map[string]any) {
		models := payload["data"].([]any)
		if len(models) != 1 {
			t.Fatalf("models len after disable = %d", len(models))
		}
	})
	req = httptest.NewRequest(http.MethodPost, "/api/dashboard/start-all", nil)
	rr = httptest.NewRecorder()
	app.Handler().ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("start all = %d body=%s", rr.Code, rr.Body.String())
	}

	req = httptest.NewRequest(http.MethodPost, "/api/dashboard/session-defaults", strings.NewReader(`{"default_tier":"premium","default_use_judge":true,"session_id_strategy":"default"}`))
	rr = httptest.NewRecorder()
	app.Handler().ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("session defaults update status = %d body=%s", rr.Code, rr.Body.String())
	}
	assertGET(t, app, "/api/dashboard/session-defaults", http.StatusOK, func(payload map[string]any) {
		data := payload["data"].(map[string]any)
		if data["default_tier"] != "premium" || data["default_use_judge"] != true {
			t.Fatalf("session defaults = %+v", data)
		}
	})

	policyBody := `{"budget_control":{"max_cost_per_session":12.5,"escalation_rate_limit":0.10,"rolling_window_size":5},"judge":{"mode":"never","complexity_threshold":0.8},"semantic_cache":{"enabled":false,"min_samples":2,"confidence_threshold":0.9,"ttl_seconds":120},"cycle_detection":{"enabled":false,"window_size":7,"simhash_distance_threshold":2}}`
	req = httptest.NewRequest(http.MethodPost, "/api/admin/policy", strings.NewReader(policyBody))
	rr = httptest.NewRecorder()
	app.Handler().ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("policy update status = %d body=%s", rr.Code, rr.Body.String())
	}
	assertGET(t, app, "/api/admin/policy", http.StatusOK, func(payload map[string]any) {
		data := payload["data"].(map[string]any)
		budget := data["budget_control"].(map[string]any)
		if budget["max_cost_per_session"].(float64) != 12.5 {
			t.Fatalf("budget policy = %+v", budget)
		}
		judge := data["judge"].(map[string]any)
		if judge["mode"] != "never" {
			t.Fatalf("judge policy = %+v", judge)
		}
		semantic := data["semantic_cache"].(map[string]any)
		if semantic["enabled"] != false || semantic["ttl_seconds"].(float64) != 120 {
			t.Fatalf("semantic policy = %+v", semantic)
		}
		cycle := data["cycle_detection"].(map[string]any)
		if cycle["enabled"] != false || cycle["window_size"].(float64) != 7 || cycle["simhash_distance_threshold"].(float64) != 2 {
			t.Fatalf("cycle policy = %+v", cycle)
		}
	})

	req = httptest.NewRequest(http.MethodPatch, "/admin/config/keys", strings.NewReader(`{"keys":{"deepseek_key":{"value":"${DEEPSEEK_API_KEY}"}}}`))
	req.Header.Set("X-Admin-Token", "admin-token")
	rr = httptest.NewRecorder()
	app.Handler().ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("key update status = %d body=%s", rr.Code, rr.Body.String())
	}

	createBody := `{"model_id":"extra-deepseek","config":{"enabled":true,"provider":"deepseek","model_id":"fake-extra-model","key_instances":["deepseek_primary"],"pricing":{"input_cost_per_m":0.1,"output_cost_per_m":0.2},"limits":{"requests_per_minute":1,"requests_per_day":10,"tokens_per_minute":1000}}}`
	req = httptest.NewRequest(http.MethodPost, "/api/dashboard/models", strings.NewReader(createBody))
	rr = httptest.NewRecorder()
	app.Handler().ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("model create status = %d body=%s", rr.Code, rr.Body.String())
	}
	req = httptest.NewRequest(http.MethodPut, "/api/dashboard/models/extra-deepseek", strings.NewReader(`{"display_name":"Extra DeepSeek"}`))
	rr = httptest.NewRecorder()
	app.Handler().ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("model update status = %d body=%s", rr.Code, rr.Body.String())
	}
	req = httptest.NewRequest(http.MethodDelete, "/api/dashboard/models/extra-deepseek", nil)
	rr = httptest.NewRecorder()
	app.Handler().ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("model delete status = %d body=%s", rr.Code, rr.Body.String())
	}

	assertGET(t, app, "/api/dashboard/configuration", http.StatusOK, func(payload map[string]any) {
		if _, ok := payload["api_keys"].(map[string]any)["deepseek_key"]; !ok {
			t.Fatalf("missing deepseek key in configuration: %+v", payload)
		}
	})
	assertGET(t, app, "/api/dashboard/full-config", http.StatusOK, func(payload map[string]any) {
		if _, ok := payload["models"].(map[string]any)["weak-deepseek"]; !ok {
			t.Fatalf("missing weak model in full config")
		}
	})
}

func TestChatRejectsInvalidRequests(t *testing.T) {
	app := newTestServer(t)
	cases := []struct {
		name string
		body string
	}{
		{name: "empty messages", body: `{"messages":[]}`},
		{name: "no user message", body: `{"messages":[{"role":"assistant","content":"hello"}]}`},
		{name: "empty content", body: `{"messages":[{"role":"user","content":""}]}`},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", strings.NewReader(tc.body))
			rr := httptest.NewRecorder()
			app.Handler().ServeHTTP(rr, req)
			if rr.Code != http.StatusBadRequest {
				t.Fatalf("status = %d body=%s", rr.Code, rr.Body.String())
			}
		})
	}
}

func newTestServer(t *testing.T) *Server {
	t.Helper()
	dir := t.TempDir()
	configPath := filepath.Join(dir, "sentinel_config.json")
	dbPath := filepath.Join(dir, "sentinelrouter.db")
	metricsPath := filepath.Join(dir, "metrics.jsonl")
	if err := os.WriteFile(configPath, []byte(testSentinelConfig()), 0o644); err != nil {
		t.Fatalf("write config: %v", err)
	}
	settings := config.LoadSettings()
	settings.SentinelConfigPath = configPath
	settings.ModelsConfigPath = filepath.Join(dir, "missing.json")
	settings.DatabaseURL = "sqlite:///" + dbPath
	settings.AdminAPIToken = "admin-token"
	settings.MaxCostPerSession = 25
	settings.InitialThreshold = 0.7
	settings.TargetEscalationRate = 0.05
	settings.RollingWindowSize = 20
	settings.CORSOrigins = "*"
	manager, err := config.NewManager(settings)
	if err != nil {
		t.Fatalf("new config manager: %v", err)
	}
	store, err := storage.Open(context.Background(), settings.DatabaseURL)
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	t.Cleanup(func() { _ = store.Close() })
	return New(settings, manager, store, metrics.NewCollector(metricsPath))
}

func assertGET(t *testing.T, app *Server, path string, status int, check func(map[string]any)) {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, path, nil)
	rr := httptest.NewRecorder()
	app.Handler().ServeHTTP(rr, req)
	if rr.Code != status {
		t.Fatalf("GET %s status = %d body=%s", path, rr.Code, rr.Body.String())
	}
	var payload map[string]any
	if err := json.NewDecoder(bytes.NewReader(rr.Body.Bytes())).Decode(&payload); err != nil {
		t.Fatalf("decode GET %s: %v", path, err)
	}
	check(payload)
}

func testSentinelConfig() string {
	return `{
  "keys": {
    "deepseek_key": {"type": "deepseek", "value": "test-key-123"},
    "anthropic_key": {"type": "anthropic", "value": "test-key-456"}
  },
  "key_instances": {
    "deepseek_primary": {"key_ref": "deepseek_key", "priority": 0, "enabled": true},
    "anthropic_primary": {"key_ref": "anthropic_key", "priority": 0, "enabled": true}
  },
  "models": {
    "weak-deepseek": {
      "enabled": true,
      "provider": "deepseek",
      "model_id": "fake-weak-model",
      "key_instances": ["deepseek_primary"],
      "pricing": {"input_cost_per_m": 0.10, "output_cost_per_m": 0.20},
      "limits": {"requests_per_minute": 60, "requests_per_day": 10000, "tokens_per_minute": 1000000}
    },
    "strong-anthropic": {
      "enabled": true,
      "provider": "anthropic",
      "model_id": "fake-strong-model",
      "key_instances": ["anthropic_primary"],
      "pricing": {"input_cost_per_m": 15.0, "output_cost_per_m": 75.0},
      "limits": {"requests_per_minute": 50, "requests_per_day": 10000, "tokens_per_minute": 80000}
    }
  },
  "routing_policy": {
    "weak_tier": {"order": ["weak-deepseek"]},
    "strong_tier": {"order": ["strong-anthropic"]}
  },
  "judge": {"enabled": false, "model_order": [], "complexity_threshold": 0.5},
  "semantic_cache": {"enabled": true, "min_samples": 3, "confidence_threshold": 0.75, "ttl_seconds": 604800}
}`
}
