package redaction

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"regexp"
	"strings"
)

type Mode string

const (
	ModeNone   Mode = "none"
	ModeLogs   Mode = "logs"
	ModeStrict Mode = "strict"
)

type Result struct {
	Text              string   `json:"redacted_text"`
	HasSensitiveData  bool     `json:"has_sensitive_data"`
	PatternsTriggered []string `json:"patterns_triggered"`
}

type pattern struct {
	name     string
	category string
	re       *regexp.Regexp
}

type Engine struct {
	mode       Mode
	strategy   string
	salt       string
	categories map[string]bool
	patterns   []pattern
}

func New(mode, strategy, salt string, categories []string) *Engine {
	m := Mode(strings.ToLower(mode))
	if m != ModeNone && m != ModeLogs && m != ModeStrict {
		m = ModeLogs
	}
	categorySet := map[string]bool{}
	for _, category := range categories {
		categorySet[strings.ToLower(strings.TrimSpace(category))] = true
	}
	return &Engine{
		mode:       m,
		strategy:   strings.ToLower(strategy),
		salt:       salt,
		categories: categorySet,
		patterns: []pattern{
			{"AWS Access Key", "aws", regexp.MustCompile(`\bAKIA[0-9A-Z]{16}\b`)},
			{"OpenAI API Key", "api_key", regexp.MustCompile(`\bsk-[A-Za-z0-9_\-]{16,}\b`)},
			{"Groq API Key", "api_key", regexp.MustCompile(`\bgsk_[A-Za-z0-9_\-]{16,}\b`)},
			{"GitHub Token", "token", regexp.MustCompile(`\bgh[pousr]_[A-Za-z0-9_]{20,}\b`)},
			{"GCP API Key", "api_key", regexp.MustCompile(`\bAIza[0-9A-Za-z_\-]{20,}\b`)},
			{"Credit Card", "pii", regexp.MustCompile(`\b(?:\d[ -]*?){13,19}\b`)},
			{"SSN", "pii", regexp.MustCompile(`\b\d{3}-\d{2}-\d{4}\b`)},
			{"Database URL", "connection", regexp.MustCompile(`(?i)\b(?:postgres|postgresql|mysql)://[^\s]+`)},
		},
	}
}

func (e *Engine) Scrub(text string) Result {
	result := Result{Text: text}
	for _, p := range e.patterns {
		if len(e.categories) > 0 && !e.categories[strings.ToLower(p.category)] {
			continue
		}
		if !p.re.MatchString(result.Text) {
			continue
		}
		result.HasSensitiveData = true
		result.PatternsTriggered = append(result.PatternsTriggered, p.name)
		result.Text = p.re.ReplaceAllStringFunc(result.Text, func(value string) string {
			return e.mask(value, p.name)
		})
	}
	return result
}

func (e *Engine) ShouldRedactForLLM() bool {
	return e.mode == ModeStrict
}

func (e *Engine) ShouldRedactForLogs() bool {
	return e.mode == ModeLogs || e.mode == ModeStrict
}

func (e *Engine) Mode() Mode {
	return e.mode
}

func (e *Engine) mask(value, name string) string {
	if e.strategy == "hmac" {
		mac := hmac.New(sha256.New, []byte(e.salt))
		_, _ = mac.Write([]byte(value))
		return "[REDACTED:" + name + ":" + hex.EncodeToString(mac.Sum(nil))[:12] + "]"
	}
	if len(value) <= 8 {
		return "[REDACTED:" + name + "]"
	}
	return value[:4] + "..." + value[len(value)-4:]
}
