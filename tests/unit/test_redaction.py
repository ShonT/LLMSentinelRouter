"""
Unit tests for redaction module.
"""

import pytest
from sentinelrouter.sentinelrouter.redaction import (
    RedactionEngine,
    RedactionMode,
    SimpleMasking,
    HMACMasking,
    CLOUDS_AND_PII_PATTERNS
)


class TestSimpleMasking:
    def test_mask_without_pattern_name(self):
        strategy = SimpleMasking()
        result = strategy.mask("sensitive-value")
        assert result == "[REDACTED]"
    
    def test_mask_with_pattern_name(self):
        strategy = SimpleMasking()
        result = strategy.mask("AKIA1234567890123456", "AWS Access Key ID")
        assert result == "[REDACTED:AWS Access Key ID]"
    
    def test_custom_placeholder(self):
        strategy = SimpleMasking(placeholder="***")
        result = strategy.mask("secret")
        assert result == "***"


class TestHMACMasking:
    def test_deterministic_masking(self):
        strategy = HMACMasking(salt="test-salt")
        result1 = strategy.mask("my-secret")
        result2 = strategy.mask("my-secret")
        assert result1 == result2
        assert result1.startswith("<REDACTED_")
        assert result1.endswith(">")
    
    def test_different_values_produce_different_hashes(self):
        strategy = HMACMasking(salt="test-salt")
        result1 = strategy.mask("secret1")
        result2 = strategy.mask("secret2")
        assert result1 != result2
    
    def test_mask_with_pattern_name(self):
        strategy = HMACMasking(salt="test-salt")
        result = strategy.mask("AKIA1234567890123456", "AWS_Access_Key_ID")
        assert "<REDACTED:AWS_Access_Key_ID:" in result
    
    def test_verify_method(self):
        strategy = HMACMasking(salt="test-salt")
        redacted = strategy.mask("my-secret")
        assert strategy.verify("my-secret", redacted) is True
        assert strategy.verify("wrong-secret", redacted) is False


class TestRedactionPatterns:
    def test_aws_access_key_detection(self):
        text = "My AWS key is AKIAIOSFODNN7EXAMPLE and it's sensitive"
        engine = RedactionEngine(mode=RedactionMode.STRICT)
        result = engine.scrub(text)
        
        assert result.has_sensitive_data
        assert "AWS Access Key ID" in result.patterns_triggered
        assert "AKIAIOSFODNN7EXAMPLE" not in result.redacted_text
        assert "[REDACTED" in result.redacted_text
    
    def test_gcp_api_key_detection(self):
        text = "Here's my Firebase key: AIzaSyD123456789012345678901234567890ABC"
        engine = RedactionEngine(mode=RedactionMode.STRICT)
        result = engine.scrub(text)
        
        assert result.has_sensitive_data
        assert "GCP API Key" in result.patterns_triggered
        assert "AIzaSyD123456789012345678901234567890ABC" not in result.redacted_text
    
    def test_ssn_detection(self):
        text = "My SSN is 123-45-6789 and it's private"
        engine = RedactionEngine(mode=RedactionMode.STRICT)
        result = engine.scrub(text)
        
        assert result.has_sensitive_data
        assert "US SSN" in result.patterns_triggered
        assert "123-45-6789" not in result.redacted_text
    
    def test_credit_card_detection(self):
        text = "Card number: 4532148803436467"
        engine = RedactionEngine(mode=RedactionMode.STRICT)
        result = engine.scrub(text)
        
        assert result.has_sensitive_data
        assert "Credit Card" in result.patterns_triggered
    
    def test_postgres_connection_string(self):
        text = "Connection: postgres://user:mypassword123@localhost:5432/db"
        engine = RedactionEngine(mode=RedactionMode.STRICT)
        result = engine.scrub(text)
        
        assert result.has_sensitive_data
        assert "PostgreSQL Connection" in result.patterns_triggered
        # Password should be redacted but rest of connection string preserved
        assert "mypassword123" not in result.redacted_text
        assert "postgres://" in result.redacted_text
    
    def test_github_token_detection(self):
        text = "My GitHub token is ghp_1234567890abcdefghijklmnopqrstuvwxyz"
        engine = RedactionEngine(mode=RedactionMode.STRICT)
        result = engine.scrub(text)
        
        assert result.has_sensitive_data
        assert "GitHub Token" in result.patterns_triggered
        assert "ghp_1234567890abcdefghijklmnopqrstuvwxyz" not in result.redacted_text
    
    def test_multiple_patterns_same_text(self):
        text = (
            "AWS key: AKIAIOSFODNN7EXAMPLE\n"
            "SSN: 123-45-6789\n"
            "Email: user@example.com"
        )
        engine = RedactionEngine(mode=RedactionMode.STRICT)
        result = engine.scrub(text)
        
        assert result.has_sensitive_data
        assert len(result.patterns_triggered) >= 3
        assert "AKIAIOSFODNN7EXAMPLE" not in result.redacted_text
        assert "123-45-6789" not in result.redacted_text
        assert "user@example.com" not in result.redacted_text


class TestRedactionEngine:
    def test_none_mode_passthrough(self):
        engine = RedactionEngine(mode=RedactionMode.NONE)
        text = "AWS key: AKIAIOSFODNN7EXAMPLE"
        result = engine.scrub(text)
        
        assert result.redacted_text == text
        assert not result.has_sensitive_data
    
    def test_logs_mode_detection(self):
        engine = RedactionEngine(mode=RedactionMode.LOGS)
        text = "AWS key: AKIAIOSFODNN7EXAMPLE"
        result = engine.scrub(text)
        
        assert result.has_sensitive_data
        assert "AKIAIOSFODNN7EXAMPLE" not in result.redacted_text
    
    def test_strict_mode_detection(self):
        engine = RedactionEngine(mode=RedactionMode.STRICT)
        text = "AWS key: AKIAIOSFODNN7EXAMPLE"
        result = engine.scrub(text)
        
        assert result.has_sensitive_data
        assert "AKIAIOSFODNN7EXAMPLE" not in result.redacted_text
    
    def test_should_redact_for_llm(self):
        engine_none = RedactionEngine(mode=RedactionMode.NONE)
        engine_logs = RedactionEngine(mode=RedactionMode.LOGS)
        engine_strict = RedactionEngine(mode=RedactionMode.STRICT)
        
        assert not engine_none.should_redact_for_llm()
        assert not engine_logs.should_redact_for_llm()
        assert engine_strict.should_redact_for_llm()
    
    def test_should_redact_for_logs(self):
        engine_none = RedactionEngine(mode=RedactionMode.NONE)
        engine_logs = RedactionEngine(mode=RedactionMode.LOGS)
        engine_strict = RedactionEngine(mode=RedactionMode.STRICT)
        
        assert not engine_none.should_redact_for_logs()
        assert engine_logs.should_redact_for_logs()
        assert engine_strict.should_redact_for_logs()
    
    def test_scrub_dict(self):
        engine = RedactionEngine(mode=RedactionMode.STRICT)
        data = {
            "message": "AWS key: AKIAIOSFODNN7EXAMPLE",
            "nested": {
                "ssn": "123-45-6789"
            },
            "items": ["safe text", "Another AWS key: AKIAIOSFODNN7EXAMPLE"]
        }
        
        result = engine.scrub_dict(data)
        
        assert "AKIAIOSFODNN7EXAMPLE" not in result["message"]
        assert "123-45-6789" not in result["nested"]["ssn"]
        assert "AKIAIOSFODNN7EXAMPLE" not in result["items"][1]
        assert result["items"][0] == "safe text"  # Unchanged
    
    def test_empty_text(self):
        engine = RedactionEngine(mode=RedactionMode.STRICT)
        result = engine.scrub("")
        
        assert result.redacted_text == ""
        assert not result.has_sensitive_data
    
    def test_category_filtering(self):
        # Only enable AWS patterns
        engine = RedactionEngine(
            mode=RedactionMode.STRICT,
            enabled_categories=["AWS"]
        )
        
        aws_text = "AWS key: AKIAIOSFODNN7EXAMPLE"
        gcp_text = "GCP key: AIzaSyDxxxxxxxxxxxxxxxxxxxxxxxxxxx123"
        
        aws_result = engine.scrub(aws_text)
        gcp_result = engine.scrub(gcp_text)
        
        # AWS should be detected
        assert aws_result.has_sensitive_data
        # GCP should NOT be detected (category not enabled)
        assert not gcp_result.has_sensitive_data
    
    def test_get_stats(self):
        engine = RedactionEngine(mode=RedactionMode.STRICT)
        stats = engine.get_stats()
        
        assert "mode" in stats
        assert stats["mode"] == "strict"
        assert "patterns_loaded" in stats
        assert "masking_strategy" in stats
        assert "pattern_names" in stats
        assert len(stats["pattern_names"]) > 0
