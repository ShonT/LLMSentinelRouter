package provider

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/ShonT/LLMSentinelRouter/internal/config"
)

type Message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
	Name    string `json:"name,omitempty"`
}

type Usage struct {
	PromptTokens     int `json:"prompt_tokens"`
	CompletionTokens int `json:"completion_tokens"`
	TotalTokens      int `json:"total_tokens"`
}

type Response struct {
	Content string `json:"content"`
	Model   string `json:"model"`
	Usage   Usage  `json:"usage"`
	Cost    float64
}

type Options struct {
	Temperature *float64
	MaxTokens   *int
	Stream      bool
}

type Client interface {
	ChatCompletion(ctx context.Context, messages []Message, opts Options) (Response, error)
	Close() error
}

type HTTPClient struct {
	provider       config.ProviderType
	apiKey         string
	modelID        string
	priceInPerM    float64
	priceOutPerM   float64
	baseURL        string
	httpClient     *http.Client
	maxRetries     int
	openRouterRef  string
	openRouterName string
}

func NewHTTPClient(provider config.ProviderType, apiKey, modelID string, pricing config.Pricing) *HTTPClient {
	client := &HTTPClient{
		provider:     provider,
		apiKey:       apiKey,
		modelID:      modelID,
		priceInPerM:  pricing.InputCostPerM,
		priceOutPerM: pricing.OutputCostPerM,
		httpClient:   &http.Client{Timeout: 60 * time.Second},
		maxRetries:   3,
	}
	switch provider {
	case config.ProviderDeepSeek:
		client.baseURL = envBaseURL("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
	case config.ProviderAnthropic:
		client.baseURL = envBaseURL("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
	case config.ProviderGemini:
		client.baseURL = envBaseURL("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
	case config.ProviderGroq:
		client.baseURL = envBaseURL("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
		client.maxRetries = 1
	case config.ProviderOpenRouter:
		client.baseURL = envBaseURL("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
		client.openRouterRef = envString("OPENROUTER_HTTP_REFERER", "http://localhost")
		client.openRouterName = envString("OPENROUTER_APP_TITLE", "LLMSentinelRouter")
	}
	return client
}

func (c *HTTPClient) ChatCompletion(ctx context.Context, messages []Message, opts Options) (Response, error) {
	if c.apiKey == "" {
		return Response{}, fmt.Errorf("%s API key not configured", c.provider)
	}
	switch c.provider {
	case config.ProviderAnthropic:
		return c.chatAnthropic(ctx, messages, opts)
	case config.ProviderGemini:
		return c.chatGemini(ctx, messages, opts)
	default:
		return c.chatOpenAICompatible(ctx, messages, opts)
	}
}

func (c *HTTPClient) Close() error {
	return nil
}

func (c *HTTPClient) chatOpenAICompatible(ctx context.Context, messages []Message, opts Options) (Response, error) {
	payload := map[string]any{
		"model":    c.modelID,
		"messages": messages,
		"stream":   opts.Stream,
	}
	if opts.Temperature != nil {
		payload["temperature"] = *opts.Temperature
	}
	if opts.MaxTokens != nil {
		payload["max_tokens"] = *opts.MaxTokens
	}
	headers := map[string]string{
		"Authorization": "Bearer " + c.apiKey,
		"Content-Type":  "application/json",
	}
	if c.provider == config.ProviderOpenRouter {
		headers["HTTP-Referer"] = c.openRouterRef
		headers["X-Title"] = c.openRouterName
	}
	data, err := c.postJSON(ctx, c.baseURL+"/chat/completions", headers, payload)
	if err != nil {
		return Response{}, err
	}
	var parsed struct {
		Choices []struct {
			Message struct {
				Content          string `json:"content"`
				ReasoningContent string `json:"reasoning_content"`
			} `json:"message"`
		} `json:"choices"`
		Usage Usage `json:"usage"`
	}
	if err := json.Unmarshal(data, &parsed); err != nil {
		return Response{}, err
	}
	content := ""
	if len(parsed.Choices) > 0 {
		content = parsed.Choices[0].Message.Content
		if content == "" {
			content = parsed.Choices[0].Message.ReasoningContent
		}
	}
	return Response{
		Content: content,
		Model:   c.modelID,
		Usage:   parsed.Usage,
		Cost:    c.cost(parsed.Usage.PromptTokens, parsed.Usage.CompletionTokens),
	}, nil
}

func (c *HTTPClient) chatAnthropic(ctx context.Context, messages []Message, opts Options) (Response, error) {
	systemParts := make([]string, 0)
	conversation := make([]Message, 0, len(messages))
	for _, msg := range messages {
		switch msg.Role {
		case "system":
			systemParts = append(systemParts, msg.Content)
		case "user", "assistant":
			conversation = append(conversation, msg)
		}
	}
	maxTokens := 4096
	if opts.MaxTokens != nil {
		maxTokens = *opts.MaxTokens
	}
	payload := map[string]any{
		"model":      c.modelID,
		"messages":   conversation,
		"max_tokens": maxTokens,
		"stream":     opts.Stream,
	}
	if opts.Temperature != nil {
		payload["temperature"] = *opts.Temperature
	}
	if len(systemParts) > 0 {
		payload["system"] = strings.Join(systemParts, "\n\n")
	}
	headers := map[string]string{
		"x-api-key":         c.apiKey,
		"anthropic-version": "2023-06-01",
		"Content-Type":      "application/json",
	}
	data, err := c.postJSON(ctx, c.baseURL+"/v1/messages", headers, payload)
	if err != nil {
		return Response{}, err
	}
	var parsed struct {
		Content []struct {
			Text string `json:"text"`
		} `json:"content"`
		Usage struct {
			InputTokens  int `json:"input_tokens"`
			OutputTokens int `json:"output_tokens"`
		} `json:"usage"`
	}
	if err := json.Unmarshal(data, &parsed); err != nil {
		return Response{}, err
	}
	content := ""
	if len(parsed.Content) > 0 {
		content = parsed.Content[0].Text
	}
	usage := Usage{
		PromptTokens:     parsed.Usage.InputTokens,
		CompletionTokens: parsed.Usage.OutputTokens,
		TotalTokens:      parsed.Usage.InputTokens + parsed.Usage.OutputTokens,
	}
	return Response{Content: content, Model: c.modelID, Usage: usage, Cost: c.cost(usage.PromptTokens, usage.CompletionTokens)}, nil
}

func (c *HTTPClient) chatGemini(ctx context.Context, messages []Message, opts Options) (Response, error) {
	contents := make([]map[string]any, 0, len(messages))
	var systemInstruction string
	for _, msg := range messages {
		switch msg.Role {
		case "system":
			systemInstruction = msg.Content
		case "user":
			contents = append(contents, map[string]any{"role": "user", "parts": []map[string]string{{"text": msg.Content}}})
		case "assistant":
			contents = append(contents, map[string]any{"role": "model", "parts": []map[string]string{{"text": msg.Content}}})
		}
	}
	payload := map[string]any{"contents": contents}
	if systemInstruction != "" {
		payload["system_instruction"] = map[string]any{"parts": []map[string]string{{"text": systemInstruction}}}
	}
	gen := map[string]any{}
	if opts.Temperature != nil {
		gen["temperature"] = *opts.Temperature
	}
	if len(gen) > 0 {
		payload["generationConfig"] = gen
	}
	headers := map[string]string{"Content-Type": "application/json"}
	data, err := c.postJSON(ctx, fmt.Sprintf("%s/models/%s:generateContent?key=%s", c.baseURL, c.modelID, c.apiKey), headers, payload)
	if err != nil {
		return Response{}, err
	}
	var parsed struct {
		Candidates []struct {
			Content struct {
				Parts []struct {
					Text string `json:"text"`
				} `json:"parts"`
			} `json:"content"`
		} `json:"candidates"`
		UsageMetadata struct {
			PromptTokenCount     int `json:"promptTokenCount"`
			CandidatesTokenCount int `json:"candidatesTokenCount"`
			TotalTokenCount      int `json:"totalTokenCount"`
		} `json:"usageMetadata"`
	}
	if err := json.Unmarshal(data, &parsed); err != nil {
		return Response{}, err
	}
	content := ""
	if len(parsed.Candidates) > 0 && len(parsed.Candidates[0].Content.Parts) > 0 {
		content = parsed.Candidates[0].Content.Parts[0].Text
	}
	usage := Usage{
		PromptTokens:     parsed.UsageMetadata.PromptTokenCount,
		CompletionTokens: parsed.UsageMetadata.CandidatesTokenCount,
		TotalTokens:      parsed.UsageMetadata.TotalTokenCount,
	}
	if usage.TotalTokens == 0 {
		usage.TotalTokens = usage.PromptTokens + usage.CompletionTokens
	}
	return Response{Content: content, Model: c.modelID, Usage: usage, Cost: c.cost(usage.PromptTokens, usage.CompletionTokens)}, nil
}

func (c *HTTPClient) postJSON(ctx context.Context, endpoint string, headers map[string]string, payload any) ([]byte, error) {
	body, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}
	var lastErr error
	for attempt := 0; attempt < c.maxRetries; attempt++ {
		req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(body))
		if err != nil {
			return nil, err
		}
		for k, v := range headers {
			req.Header.Set(k, v)
		}
		resp, err := c.httpClient.Do(req)
		if err != nil {
			lastErr = err
			if ctx.Err() != nil {
				return nil, lastErr
			}
			time.Sleep(time.Duration(attempt+1) * time.Second)
			continue
		}
		respBody, readErr := io.ReadAll(resp.Body)
		_ = resp.Body.Close()
		if readErr != nil {
			return nil, readErr
		}
		if resp.StatusCode >= 200 && resp.StatusCode < 300 {
			return respBody, nil
		}
		lastErr = fmt.Errorf("provider %s returned HTTP %d: %s", c.provider, resp.StatusCode, string(respBody))
		if resp.StatusCode == http.StatusTooManyRequests || resp.StatusCode == http.StatusServiceUnavailable {
			if c.provider == config.ProviderGroq {
				return nil, lastErr
			}
			time.Sleep(time.Duration(1<<attempt) * time.Second)
			continue
		}
		return nil, lastErr
	}
	if lastErr == nil {
		lastErr = errors.New("provider request failed")
	}
	return nil, lastErr
}

func (c *HTTPClient) cost(inputTokens, outputTokens int) float64 {
	return (float64(inputTokens)*c.priceInPerM + float64(outputTokens)*c.priceOutPerM) / 1_000_000
}

type Factory struct{}

func (Factory) NewClient(providerType config.ProviderType, apiKey string, model config.ModelDefinition) Client {
	return NewHTTPClient(providerType, apiKey, model.ModelID, model.Pricing)
}

func ValidateProviderKey(ctx context.Context, providerType config.ProviderType, apiKey string, timeout time.Duration) (bool, string) {
	if strings.TrimSpace(apiKey) == "" {
		return false, "API key is empty."
	}
	if timeout <= 0 {
		timeout = 10 * time.Second
	}
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	req, err := validationRequest(ctx, providerType, apiKey)
	if err != nil {
		return false, err.Error()
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return false, "Validation failed due to network error."
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 200 && resp.StatusCode < 300 {
		return true, "Key valid."
	}
	if resp.StatusCode == http.StatusUnauthorized || resp.StatusCode == http.StatusForbidden {
		return false, "Invalid key or insufficient permissions."
	}
	return false, fmt.Sprintf("Provider returned HTTP %d.", resp.StatusCode)
}

func validationRequest(ctx context.Context, providerType config.ProviderType, apiKey string) (*http.Request, error) {
	switch providerType {
	case config.ProviderDeepSeek:
		req, _ := http.NewRequestWithContext(ctx, http.MethodGet, envBaseURL("DEEPSEEK_BASE_URL", "https://api.deepseek.com")+"/models", nil)
		req.Header.Set("Authorization", "Bearer "+apiKey)
		return req, nil
	case config.ProviderOpenRouter:
		req, _ := http.NewRequestWithContext(ctx, http.MethodGet, envBaseURL("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")+"/models", nil)
		req.Header.Set("Authorization", "Bearer "+apiKey)
		return req, nil
	case config.ProviderGroq:
		req, _ := http.NewRequestWithContext(ctx, http.MethodGet, envBaseURL("GROQ_BASE_URL", "https://api.groq.com/openai/v1")+"/models", nil)
		req.Header.Set("Authorization", "Bearer "+apiKey)
		return req, nil
	case config.ProviderAnthropic:
		req, _ := http.NewRequestWithContext(ctx, http.MethodGet, envBaseURL("ANTHROPIC_BASE_URL", "https://api.anthropic.com")+"/v1/models", nil)
		req.Header.Set("x-api-key", apiKey)
		req.Header.Set("anthropic-version", "2023-06-01")
		return req, nil
	case config.ProviderGemini:
		return http.NewRequestWithContext(ctx, http.MethodGet, envBaseURL("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")+"/models?key="+apiKey, nil)
	default:
		return nil, fmt.Errorf("unsupported provider %q", providerType)
	}
}

func envBaseURL(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return strings.TrimRight(value, "/")
	}
	return fallback
}

func envString(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}
