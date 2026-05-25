package provider

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/ShonT/LLMSentinelRouter/internal/config"
)

func TestMessageUnmarshalJSONStringContent(t *testing.T) {
	raw := `{"role":"user","content":"hello world"}`
	var msg Message
	if err := json.Unmarshal([]byte(raw), &msg); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if msg.Role != "user" {
		t.Fatalf("role = %q", msg.Role)
	}
	if msg.Content != "hello world" {
		t.Fatalf("content = %q", msg.Content)
	}
}

func TestMessageUnmarshalJSONNullContent(t *testing.T) {
	raw := `{"role":"assistant","content":null}`
	var msg Message
	if err := json.Unmarshal([]byte(raw), &msg); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if msg.Content != "" {
		t.Fatalf("content = %q, want empty", msg.Content)
	}
}

func TestMessageUnmarshalJSONArrayContent(t *testing.T) {
	raw := `{"role":"user","content":[{"type":"text","text":"hello"}]}`
	var msg Message
	if err := json.Unmarshal([]byte(raw), &msg); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if msg.Content == "" {
		t.Fatal("non-string content should be coerced to string representation")
	}
}

func TestMessageUnmarshalJSONMissingContent(t *testing.T) {
	raw := `{"role":"user"}`
	var msg Message
	if err := json.Unmarshal([]byte(raw), &msg); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if msg.Content != "" {
		t.Fatalf("content = %q, want empty", msg.Content)
	}
}

func TestChatOpenAICompatible(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/chat/completions" {
			t.Fatalf("path = %q", r.URL.Path)
		}
		var payload map[string]any
		_ = json.NewDecoder(r.Body).Decode(&payload)
		if payload["model"] != "test-model" {
			t.Fatalf("model = %v", payload["model"])
		}
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprint(w, `{"choices":[{"message":{"content":"reply"}}],"usage":{"prompt_tokens":10,"completion_tokens":5,"total_tokens":15}}`)
	}))
	defer server.Close()
	t.Setenv("DEEPSEEK_BASE_URL", server.URL)

	client := NewHTTPClient(config.ProviderDeepSeek, "test-key", "test-model", config.Pricing{InputCostPerM: 0.1, OutputCostPerM: 0.2})
	resp, err := client.ChatCompletion(context.Background(), []Message{{Role: "user", Content: "hello"}}, Options{})
	if err != nil {
		t.Fatalf("chat: %v", err)
	}
	if resp.Content != "reply" {
		t.Fatalf("content = %q", resp.Content)
	}
	if resp.Usage.TotalTokens != 15 {
		t.Fatalf("tokens = %d", resp.Usage.TotalTokens)
	}
}

func TestChatCompletionStreamOpenAI(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		fmt.Fprint(w, "data: {\"choices\":[{\"delta\":{\"content\":\"hel\"}}]}\n\n")
		fmt.Fprint(w, "data: {\"choices\":[{\"delta\":{\"content\":\"lo\"}}],\"usage\":{\"prompt_tokens\":1,\"completion_tokens\":1,\"total_tokens\":2}}\n\n")
		fmt.Fprint(w, "data: [DONE]\n\n")
	}))
	defer server.Close()
	t.Setenv("DEEPSEEK_BASE_URL", server.URL)

	client := NewHTTPClient(config.ProviderDeepSeek, "test-key", "test-model", config.Pricing{})
	var chunks []string
	resp, err := client.ChatCompletionStream(context.Background(),
		[]Message{{Role: "user", Content: "hi"}}, Options{Stream: true},
		func(chunk StreamChunk) error {
			if chunk.Content != "" {
				chunks = append(chunks, chunk.Content)
			}
			return nil
		},
	)
	if err != nil {
		t.Fatalf("stream: %v", err)
	}
	if resp.Content != "hello" {
		t.Fatalf("content = %q, want hello", resp.Content)
	}
	if len(chunks) != 2 {
		t.Fatalf("chunks = %d, want 2", len(chunks))
	}
}

func TestChatAnthropicFormat(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/messages" {
			t.Fatalf("path = %q", r.URL.Path)
		}
		if r.Header.Get("x-api-key") != "test-key" {
			t.Fatalf("api-key = %q", r.Header.Get("x-api-key"))
		}
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprint(w, `{"content":[{"text":"anthropic reply"}],"usage":{"input_tokens":5,"output_tokens":10}}`)
	}))
	defer server.Close()
	t.Setenv("ANTHROPIC_BASE_URL", server.URL)

	client := NewHTTPClient(config.ProviderAnthropic, "test-key", "claude-3", config.Pricing{InputCostPerM: 15, OutputCostPerM: 75})
	resp, err := client.ChatCompletion(context.Background(), []Message{
		{Role: "system", Content: "you are helpful"},
		{Role: "user", Content: "hello"},
	}, Options{})
	if err != nil {
		t.Fatalf("chat: %v", err)
	}
	if resp.Content != "anthropic reply" {
		t.Fatalf("content = %q", resp.Content)
	}
	if resp.Usage.PromptTokens != 5 || resp.Usage.CompletionTokens != 10 {
		t.Fatalf("usage = %+v", resp.Usage)
	}
}

func TestChatGeminiFormat(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprint(w, `{"candidates":[{"content":{"parts":[{"text":"gemini reply"}]}}],"usageMetadata":{"promptTokenCount":3,"candidatesTokenCount":7,"totalTokenCount":10}}`)
	}))
	defer server.Close()
	t.Setenv("GEMINI_BASE_URL", server.URL)

	client := NewHTTPClient(config.ProviderGemini, "test-key", "gemini-flash", config.Pricing{InputCostPerM: 0.5, OutputCostPerM: 1.5})
	resp, err := client.ChatCompletion(context.Background(), []Message{{Role: "user", Content: "hi"}}, Options{})
	if err != nil {
		t.Fatalf("chat: %v", err)
	}
	if resp.Content != "gemini reply" {
		t.Fatalf("content = %q", resp.Content)
	}
	if resp.Usage.TotalTokens != 10 {
		t.Fatalf("tokens = %d", resp.Usage.TotalTokens)
	}
}

func TestChatFailsWithEmptyKey(t *testing.T) {
	client := NewHTTPClient(config.ProviderDeepSeek, "", "model", config.Pricing{})
	_, err := client.ChatCompletion(context.Background(), []Message{{Role: "user", Content: "hi"}}, Options{})
	if err == nil {
		t.Fatal("expected error for empty key")
	}
}

func TestCostCalculation(t *testing.T) {
	client := &HTTPClient{priceInPerM: 1.0, priceOutPerM: 2.0}
	cost := client.cost(1000, 500)
	expected := (1000*1.0 + 500*2.0) / 1_000_000
	if cost != expected {
		t.Fatalf("cost = %g, want %g", cost, expected)
	}
}

func TestStreamHandlerNilFallsBackToNonStreaming(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprint(w, `{"choices":[{"message":{"content":"reply"}}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}`)
	}))
	defer server.Close()
	t.Setenv("DEEPSEEK_BASE_URL", server.URL)

	client := NewHTTPClient(config.ProviderDeepSeek, "key", "model", config.Pricing{})
	resp, err := client.ChatCompletionStream(context.Background(), []Message{{Role: "user", Content: "hi"}}, Options{}, nil)
	if err != nil {
		t.Fatalf("stream with nil handler: %v", err)
	}
	if resp.Content != "reply" {
		t.Fatalf("content = %q", resp.Content)
	}
}

func TestFactoryNewClient(t *testing.T) {
	f := Factory{}
	client := f.NewClient(config.ProviderDeepSeek, "key", config.ModelDefinition{
		Provider: config.ProviderDeepSeek,
		ModelID:  "test-model",
		Pricing:  config.Pricing{InputCostPerM: 1.0},
	})
	if client == nil {
		t.Fatal("factory returned nil client")
	}
	_ = client.Close()
}
