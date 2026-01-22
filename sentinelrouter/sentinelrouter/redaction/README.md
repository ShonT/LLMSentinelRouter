# Redaction System

Comprehensive sensitive data protection for LLMSentinelRouter with pattern-based detection and configurable masking strategies.

## Features

- **Multi-Cloud Coverage**: AWS, GCP, Azure credentials
- **PII Protection**: SSN, credit cards, phone numbers, emails, IP addresses
- **Database Security**: Connection string password redaction
- **Version Control**: GitHub, GitLab tokens
- **Flexible Masking**: Simple placeholders or HMAC-based deterministic hashing
- **Three Operating Modes**: NONE, LOGS, STRICT

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   RedactionEngine                       │
├─────────────────────────────────────────────────────────┤
│  Mode: NONE | LOGS | STRICT                            │
│  ├─ Pattern Registry (40+ patterns)                    │
│  ├─ Masking Strategy (Simple | HMAC)                   │
│  └─ Category Filtering (AWS, GCP, Azure, PII, etc.)    │
└─────────────────────────────────────────────────────────┘
```

## Operating Modes

### NONE (Disabled)
- No redaction occurs
- Passthrough mode for debugging or low-security environments

### LOGS (Default)
- **LLM sees**: Original prompt with sensitive data
- **Audit logs see**: Redacted version
- Use case: Trust the LLM provider, but want secure audit trails

### STRICT (Maximum Security)
- **LLM sees**: Redacted version (`<REDACTED_7a12b9f4c3>`)
- **Audit logs see**: Redacted version
- Use case: Zero-trust with LLM providers, compliance requirements

## Configuration

### Environment Variables

```bash
# Mode: "none", "logs", or "strict"
REDACTION_MODE=logs

# Strategy: "simple" or "hmac"
REDACTION_STRATEGY=hmac

# Salt for HMAC (change in production!)
REDACTION_SALT=your-secure-random-salt-here

# Filter by categories (comma-separated, empty = all)
REDACTION_CATEGORIES=AWS,PII,Database
```

### Programmatic Configuration

```python
from sentinelrouter.sentinelrouter.redaction import (
    RedactionEngine,
    RedactionMode,
    HMACMasking
)

# Initialize with HMAC strategy
engine = RedactionEngine(
    mode=RedactionMode.STRICT,
    masking_strategy=HMACMasking(salt="my-secret-salt"),
    enabled_categories=["AWS", "PII"]
)

# Scrub text
result = engine.scrub("My AWS key is AKIAIOSFODNN7EXAMPLE")
print(result.redacted_text)
# Output: "My AWS key is <REDACTED:AWS_Access_Key_ID:7a12b9f4c3>"
```

## Pattern Categories

| Category | Patterns | Examples |
|----------|----------|----------|
| **AWS** | Access Keys, Secret Keys, Session Tokens | `AKIA...`, `aws_secret_access_key` |
| **GCP** | API Keys, OAuth Client IDs, Service Accounts | `AIza...`, `*.apps.googleusercontent.com` |
| **Azure** | Storage Keys, Client Secrets, Subscription Keys | Connection strings, app secrets |
| **PII** | SSN, Credit Cards, Phone, Email, IP | `123-45-6789`, `4532-1488-...` |
| **Database** | PostgreSQL, MySQL, MongoDB | `postgres://user:password@host` |
| **Generic** | API Keys, Bearer Tokens, Private Keys | `api_key: ...`, `Bearer ...` |
| **VCS** | GitHub, GitLab tokens | `ghp_...`, `glpat-...` |
| **Collaboration** | Slack tokens, webhooks | `xoxb-...`, Slack webhook URLs |

## Masking Strategies

### Simple Masking (Fast)
```python
strategy = SimpleMasking(placeholder="[REDACTED]")
result = strategy.mask("my-secret")
# Output: "[REDACTED]"
```

**Pros**: Fastest, no configuration needed  
**Cons**: No way to correlate multiple occurrences

### HMAC Masking (Staff-Level)
```python
strategy = HMACMasking(salt="my-salt", hash_length=10)
result = strategy.mask("my-secret")
# Output: "<REDACTED_7a12b9f4c3>"
```

**Pros**:
- Deterministic: Same value → same hash
- Stateless: No database required
- Collision-resistant (SHA256)
- Reversible with salt (for authorized audits)
- Enables correlation and debugging

**Cons**:
- Slightly slower than simple masking
- Requires secure salt management

## Integration with Router

The redaction engine is automatically initialized in the Router and applies based on the configured mode:

```python
# router_logic.py
class Router:
    def __init__(self, db_session):
        # ... other initialization
        self.redaction_engine = self._init_redaction_engine()
    
    async def route(self, session_id, prompt, messages, ...):
        # 0. Redaction - Scan for sensitive data
        redaction_result = self.redaction_engine.scrub(prompt)
        
        # Apply STRICT mode redaction (LLM sees redacted)
        if self.redaction_engine.should_redact_for_llm():
            prompt = redaction_result.redacted_text
        
        # ... routing logic ...
        
        # Apply LOGS mode redaction (audit logs see redacted)
        if self.redaction_engine.should_redact_for_logs():
            log_prompt = redaction_result.redacted_text
```

## API Usage

### Check Current Mode

```http
GET /api/redaction/status
```

Response:
```json
{
  "mode": "logs",
  "patterns_loaded": 40,
  "masking_strategy": "HMACMasking",
  "enabled_categories": ["AWS", "GCP", "Azure", "PII"]
}
```

### Test Redaction (Admin Only)

```http
POST /api/redaction/test
Content-Type: application/json

{
  "text": "My AWS key is AKIAIOSFODNN7EXAMPLE",
  "mode": "strict"
}
```

Response:
```json
{
  "original": "My AWS key is AKIAIOSFODNN7EXAMPLE",
  "redacted": "My AWS key is <REDACTED:AWS_Access_Key_ID:7a12b9f4c3>",
  "has_sensitive_data": true,
  "patterns_triggered": {
    "AWS Access Key ID": 1
  }
}
```

## Testing

```bash
# Run redaction tests
pytest tests/unit/test_redaction.py -v

# Test specific pattern category
pytest tests/unit/test_redaction.py::TestRedactionPatterns::test_aws_access_key_detection -v
```

## Adding Custom Patterns

```python
from sentinelrouter.sentinelrouter.redaction.patterns import RedactionPattern
import re

# Define custom pattern
custom_pattern = RedactionPattern(
    name="Custom Secret",
    regex=re.compile(r"secret_[a-zA-Z0-9]{20}"),
    description="Matches custom secret format"
)

# Add to engine
from sentinelrouter.sentinelrouter.redaction.patterns import CLOUDS_AND_PII_PATTERNS
CLOUDS_AND_PII_PATTERNS.append(custom_pattern)

# Or create engine with custom patterns
engine = RedactionEngine(
    mode=RedactionMode.STRICT,
    patterns=[custom_pattern]
)
```

## Performance

- **Pattern Matching**: O(n) where n is text length
- **Simple Masking**: ~0.1ms per match
- **HMAC Masking**: ~0.5ms per match
- **Overhead**: < 1ms for typical prompts (<1KB)

## Security Best Practices

1. **Change Default Salt**: Never use default HMAC salt in production
2. **Rotate Salts**: Periodically rotate HMAC salts (requires re-redaction)
3. **Secure Storage**: Store salt in secrets manager (e.g., AWS Secrets Manager)
4. **Audit Logs**: Monitor redaction events for security incidents
5. **Test Coverage**: Regularly test with real-world data samples
6. **Category Selection**: Only enable needed categories to reduce false positives

## Troubleshooting

### False Positives

If valid data is being redacted:
1. Review pattern regex in `patterns.py`
2. Disable specific categories: `REDACTION_CATEGORIES=PII`
3. Use `engine.scrub(text)` to debug what's being matched

### False Negatives

If sensitive data isn't being caught:
1. Check pattern regex coverage
2. Add custom patterns for your specific format
3. Review logs: `logger.warning("Sensitive data detected: ...")`

### Performance Issues

If redaction is slow:
1. Switch to `SimpleMasking` strategy
2. Reduce enabled categories
3. Cache redaction results for repeated prompts

## Future Enhancements

- [ ] ML-based pattern detection for novel secrets
- [ ] Real-time pattern updates from threat intelligence
- [ ] Distributed caching for HMAC results
- [ ] Admin UI for pattern management
- [ ] Custom pattern editor with regex tester
- [ ] Redaction analytics dashboard

## References

- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [AWS Access Key Format](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_identifiers.html)
- [NIST PII Guide](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-122.pdf)
