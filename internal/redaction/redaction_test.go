package redaction

import "testing"

func TestRedactionModesAndMasking(t *testing.T) {
	engine := New("strict", "hmac", "salt", nil)
	result := engine.Scrub("token sk-abcdefghijklmnop and card 4111 1111 1111 1111")
	if !result.HasSensitiveData {
		t.Fatal("expected sensitive data")
	}
	if result.Text == "token sk-abcdefghijklmnop and card 4111 1111 1111 1111" {
		t.Fatal("text was not redacted")
	}
	if !engine.ShouldRedactForLLM() || !engine.ShouldRedactForLogs() {
		t.Fatal("strict mode should redact for LLM and logs")
	}
}
