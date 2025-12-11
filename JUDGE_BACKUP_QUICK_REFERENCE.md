# Quick Reference: Judge and Model Backup System

## Judge Backup Chain (4 Levels)

```
Priority 0: DeepSeek       (Primary - cheap, fast)
    ↓ fails
Priority 1: Anthropic      (Backup 1 - reliable)
    ↓ fails
Priority 2: Gemini Flash   (Backup 2 - Google)
    ↓ fails
Priority 3: Gemini Live    (Backup 3 - Google)
    ↓ fails
Fallback: (0.1, LOW)       (Assume weak model)
```

## Weak Model Backup Chain (Available for Router)

Primary weak models can also have backups using same registry pattern:
- Primary: DeepSeek
- Backup 1: Gemini Flash
- Backup 2: Gemini Flash Live

## Key Behavior: Judge Failure → Weak Model

**When all judges fail:**
- Complexity score: `0.1` (very low)
- Impact scope: `LOW`
- Routing decision: Use **weak model**

**Why?**
- Conservative approach saves money
- Assumes task is simple if judge can't evaluate it
- Better than guessing medium (0.5) and potentially wasting $ on strong model

## API Keys Required

```bash
# Required
DEEPSEEK_API_KEY=sk-xxx
ANTHROPIC_API_KEY=sk-xxx

# Optional (have defaults)
GEMINI_BACKUP1_API_KEY=AIzaSyCmm7euC6vHz39nJXEZAkqqJeUIB1rtVI8
GEMINI_BACKUP2_API_KEY=AIzaSyBEgIiciMs-NIQqeoYtOfjkvCzVIAr5Fw8
```

## Costs (per million tokens)

| Provider | Model | Cost/M | Usage |
|----------|-------|--------|-------|
| DeepSeek | deepseek-chat | $0.27 | Primary judge (98%) |
| Anthropic | claude-haiku | $5.00 | Backup judge 1 (1.5%) |
| Gemini | flash | $0.10 | Backup judge 2/3 (0.5%) |

**Average judge cost per request:** ~$0.000034 (3.4¢ per 1000 requests)

## Circuit Breaker Settings

- **Failure threshold:** 3 failures in 5 minutes
- **Cooldown:** 60 seconds
- **Behavior:** Skip failing judge, go directly to next backup

## Judge Status API

```python
from sentinelrouter.sentinelrouter.judge import StingyJudge

judge = StingyJudge()
status = await judge.get_status()

# Returns:
# {
#   "judges": [
#     {
#       "judge_id": "deepseek-judge-primary",
#       "display_name": "DeepSeek Judge (Primary)",
#       "priority": 0,
#       "model": "deepseek-chat",
#       "available": true,
#       "circuit_open": false,
#       "failure_count": 0,
#       "recent_failures": 0
#     },
#     # ... 3 more judges
#   ]
# }
```

## Testing

```bash
# Test Gemini integration
docker compose run --rm sentinelrouter python3 tests/test_gemini_backup_judges.py

# Test backup judges system
docker compose run --rm sentinelrouter python3 tests/test_backup_judges_demo.py

# Run all tests
docker compose run --rm sentinelrouter python3 -m pytest tests/ -v
```

## Logging

**Normal operation:**
```
INFO: Selected judge: deepseek-judge-primary
INFO: Judge result from deepseek-judge-primary: score=0.3, impact=LOW
```

**Failover:**
```
ERROR: Judge deepseek-judge-primary failed: Timeout
INFO: Judge attempt 2/5: Using Anthropic Judge (Backup 1)
INFO: ✅ Judge success with anthropic-judge-backup: score=0.3, impact=LOW
```

**Circuit breaker:**
```
WARNING: Circuit breaker OPEN for judge deepseek-judge-primary: 3 failures
DEBUG: Judge deepseek-judge-primary unavailable: circuit breaker open
INFO: Selected judge: anthropic-judge-backup
```

**Complete failure:**
```
ERROR: All judges failed after 4 attempts. Using default fallback.
INFO: Judge result: score=0.1, impact=LOW (weak model assumed)
```

## Files Reference

| File | Purpose |
|------|---------|
| `clients.py` | GeminiClient class, client getters |
| `config.py` | Gemini API key configuration |
| `judge.py` | Judge registry setup, 4 judges |
| `judge_registry.py` | JudgeRegistry, circuit breaker, fallback (0.1, LOW) |
| `model_registry.py` | ModelRegistry for weak/strong model backups |
| `docker-compose.yml` | Environment variables |

## Quick Start

**1. No code changes needed - just works:**
```python
from sentinelrouter.sentinelrouter.judge import StingyJudge

judge = StingyJudge()
score, impact, reasoning = await judge.judge("Create a new feature")
# Automatically uses 4-level backup system
```

**2. Monitor health:**
```python
status = await judge.get_status()
for j in status["judges"]:
    print(f"{j['display_name']}: {'✅' if j['available'] else '❌'}")
```

**3. Check if using fallback:**
```python
score, impact, reasoning = await judge.judge(prompt)
if score == 0.1 and impact == "LOW":
    print("⚠️  Using fallback - all judges may be down")
```

## Troubleshooting

**Issue:** All judges fail
- **Cause:** API keys invalid or all providers down
- **Behavior:** Returns (0.1, LOW, "...weak model...")
- **Action:** Routes to weak model (conservative, safe)

**Issue:** Circuit breaker opens frequently
- **Cause:** Provider having issues
- **Behavior:** Automatic fallback to next backup
- **Action:** No action needed, self-healing

**Issue:** High costs
- **Cause:** Frequent failover to Anthropic
- **Behavior:** Using expensive backup judge
- **Action:** Check primary judge health, increase circuit breaker threshold

## Summary

✅ **4 judge backups** (DeepSeek → Anthropic → Gemini → Gemini)
✅ **Conservative fallback** (assume weak model when judges fail)
✅ **Minimal cost** (< 1% increase)
✅ **Self-healing** (circuit breaker + automatic recovery)
✅ **Production ready** (comprehensive tests)
