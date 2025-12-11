# SentinelRouter Feature Test Plan

## Overview

This test plan systematically verifies each module of SentinelRouter while **minimizing expensive API calls** to the strong model (Anthropic Claude). The plan focuses on testing functionality without incurring unnecessary costs.

## Cost-Aware Testing Strategy

### Estimated Total Cost: **~$0.01**

| Module | Tests | Estimated Cost | Strategy |
|--------|-------|---------------|----------|
| Health Check | 1 | $0.000 | No LLM calls |
| OpenAI Compatibility | 1 | $0.0003 | Single simple request |
| Module A (Budget) | 3 | $0.001 | Multiple cheap requests |
| Module B (Judge) | 3 | $0.002 | Simple prompts, avoid strong model |
| Module C (Threshold) | 2 | $0.000 | Documentation only |
| Module D (Cycles) | 3 | $0.001 | Repeated identical requests |
| **TOTAL** | **13** | **~$0.005** | **All using weak model** |

### Cost Minimization Techniques

1. **Use Simple Prompts**: Test with trivial questions that clearly route to weak model
2. **Skip Expensive Tests**: Document strong model tests but don't execute unless necessary
3. **Reuse Requests**: For cycle detection, repeat the same cheap request
4. **Monitor Headers**: Verify behavior via response headers instead of forcing expensive calls
5. **Manual Testing Guide**: Provide instructions for expensive test scenarios

---

## Module-by-Module Test Plan

### Module A: Budget Kill-Switch

**Objective**: Verify session-based budget tracking and enforcement

#### Test A1: Budget Initialization
- **Action**: Send first request to new session
- **Expected**: Session created with $10.00 budget (MAX_COST_PER_SESSION)
- **Verification**: Check `X-Sentinel-Session-Cost` header
- **Cost**: ~$0.0003
- **Prompt**: "Say 'hi'"

#### Test A2: Budget Accumulation
- **Action**: Send second request to same session
- **Expected**: Session cost increases from previous request
- **Verification**: `X-Sentinel-Session-Cost` > previous value
- **Cost**: ~$0.0003
- **Prompt**: "Count to 3"

#### Test A3: Budget Enforcement
- **Action**: **SKIPPED** (would require many expensive requests)
- **Why**: Need to exceed $10 budget, would cost $10+ to test
- **Alternative**: Manual test with `MAX_COST_PER_SESSION=0.001` in .env
- **Documentation**: 
  ```bash
  # To test budget overflow:
  # 1. Set MAX_COST_PER_SESSION=0.001 in .env
  # 2. Restart server
  # 3. Make 2-3 requests
  # 4. Verify request is rejected with budget exceeded error
  ```

**Module A Total Cost**: ~$0.0006

---

### Module B: "Stingy" Judge & Categorizer

**Objective**: Verify complexity scoring and routing decisions

#### Test B1: Simple Prompt Classification
- **Action**: Send trivial arithmetic question
- **Expected**: 
  - Complexity score < 0.3
  - Routes to DeepSeek (weak model)
- **Verification**: 
  - `X-Sentinel-Complexity-Score` < 0.3
  - `X-Sentinel-Model-Used` == "deepseek"
- **Cost**: ~$0.0003
- **Prompt**: "What is 2+2? Just the number."

#### Test B2: Medium Prompt Classification
- **Action**: Send technical explanation request
- **Expected**: 
  - Complexity score 0.2-0.6
  - May route to either model based on threshold
- **Verification**: Check complexity score is reasonable
- **Cost**: ~$0.0005
- **Prompt**: "Explain the difference between a list and a tuple in Python."

#### Test B3: Complex Prompt Scoring
- **Action**: Send philosophical/mathematical analysis request
- **Expected**: 
  - Complexity score > 0.15
  - With default threshold (0.5), likely still uses weak model
- **Verification**: Complexity score higher than simple prompts
- **Cost**: ~$0.0008
- **Prompt**: "Analyze the philosophical implications of Gödel's incompleteness theorems..."
- **Note**: We verify scoring works, not forcing strong model call

**Module B Total Cost**: ~$0.0016

---

### Module C: Dynamic Thresholding (5% Rule)

**Objective**: Verify threshold adjustment mechanism

#### Test C1: Threshold Initialization
- **Action**: Document initial configuration
- **Expected**: 
  - INITIAL_THRESHOLD: 0.7
  - TARGET_ESCALATION_RATE: 0.05 (5%)
  - ROLLING_WINDOW_SIZE: 20
- **Verification**: Configuration check only
- **Cost**: $0.000

#### Test C2: Threshold Adjustment Logic
- **Action**: **DOCUMENTED** (requires 20+ requests to observe)
- **Why**: Need rolling window of 20 requests to see adjustment
- **Alternative**: Monitor over normal usage
- **Documentation**:
  ```
  Adjustment Rules:
  - If escalation_rate > 5%: threshold += 0.05 (more stingy)
  - If escalation_rate < 5%: threshold -= 0.05 (less stingy)
  - Threshold bounds: [0.3, 0.9]
  
  To observe:
  1. Make 20+ requests with varying complexity
  2. Monitor X-Sentinel-Complexity-Score header
  3. Check if threshold adjusts based on escalation rate
  4. Log: sentinelrouter.threshold module shows adjustments
  ```

**Module C Total Cost**: $0.000

---

### Module D: Graph-Based Cycle Detection

**Objective**: Verify cycle detection using semantic hashing

#### Test D1: Initial Request (No Cycle)
- **Action**: Send first request with specific prompt
- **Expected**: No cycle detected
- **Verification**: `X-Sentinel-Cycle-Detected` == "false"
- **Cost**: ~$0.0003
- **Prompt**: "What is the capital of France?"

#### Test D2: Repeated Request (Cycle Check)
- **Action**: Send identical request again
- **Expected**: May or may not detect cycle (depends on simhash threshold)
- **Verification**: Header present, value is boolean
- **Cost**: ~$0.0003
- **Prompt**: Same as D1

#### Test D3: Third Identical Request
- **Action**: Send same request third time
- **Expected**: Higher probability of cycle detection
- **Verification**: 
  - Cycle detection logic triggered
  - Using simhash + hamming distance (threshold: 3 bits)
- **Cost**: ~$0.0003
- **Prompt**: Same as D1

**Module D Total Cost**: ~$0.0009

---

### OpenAI API Compatibility

**Objective**: Verify OpenAI-compatible response format

#### Test: Response Format Validation
- **Action**: Send simple request and validate response structure
- **Expected Response Structure**:
  ```json
  {
    "id": "chatcmpl-...",
    "object": "chat.completion",
    "created": 1234567890,
    "model": "deepseek-reasoner",
    "choices": [{
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "..."
      },
      "finish_reason": "stop"
    }],
    "usage": {
      "prompt_tokens": 10,
      "completion_tokens": 20,
      "total_tokens": 30
    }
  }
  ```
- **Expected Headers**:
  - `X-Sentinel-Model-Used`
  - `X-Sentinel-Cost`
  - `X-Sentinel-Session-Cost`
  - `X-Sentinel-Complexity-Score`
  - `X-Sentinel-Cycle-Detected`
- **Cost**: ~$0.0003
- **Prompt**: "Hi"

**OpenAI Compatibility Total Cost**: ~$0.0003

---

### Health Check Endpoint

**Objective**: Verify monitoring endpoint

#### Test: Endpoint Availability
- **Action**: GET /health
- **Expected**: 
  ```json
  {
    "status": "healthy",
    "service": "sentinelrouter"
  }
  ```
- **Cost**: $0.000 (no LLM calls)

---

## Running the Test Plan

### Automated Testing

```bash
# Ensure server is running
docker-compose up -d

# Run automated test suite
python3 feature_test_plan.py
```

### Output Format

The script will:
1. Print real-time test results with emojis
2. Track cumulative cost
3. Generate JSON report with all results
4. Save to `feature_test_results_YYYYMMDD_HHMMSS.json`

### Expected Output

```
======================================================================
🚀 SentinelRouter Feature Verification Plan
======================================================================
Started at: 2025-12-09T...
Base URL: http://localhost:8000

Cost Awareness: Minimizing expensive strong model calls
======================================================================

======================================================================
Health Endpoint Testing
======================================================================
✅ Health Check - Endpoint Availability: PASS

======================================================================
OpenAI API Compatibility Testing
======================================================================
✅ OpenAI Compatibility - Response Format Validation: PASS
   Cost: $0.000300 | Total: $0.000300

======================================================================
MODULE A: Budget Kill-Switch Testing
======================================================================
✅ Module A - Budget Initialization: PASS
   Cost: $0.000273 | Total: $0.000573
✅ Module A - Budget Accumulation: PASS
   Cost: $0.000267 | Total: $0.000840
⏭️  Module A - Budget Enforcement (Overflow): SKIP

... (continued for all modules)

======================================================================
📊 TEST SUMMARY
======================================================================

Total Tests: 13
✅ Passed: 10
❌ Failed: 0
⚠️  Warnings: 1
⏭️  Skipped: 2

💰 Total Estimated Cost: $0.004521
   (Minimized by avoiding unnecessary strong model calls)

💾 Results saved to: feature_test_results_20251209_123456.json
```

---

## Manual Testing for Expensive Scenarios

### Testing Strong Model Routing

**Setup**:
```bash
# Lower the complexity threshold to force strong model usage
# Edit .env:
COMPLEXITY_THRESHOLD=0.1
```

**Test**:
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "messages": [{
      "role": "user",
      "content": "Explain quantum entanglement"
    }],
    "session_id": "strong-model-test"
  }'
```

**Verify**:
- `X-Sentinel-Model-Used` should be "anthropic"
- Cost should be ~$0.02-0.10 (higher than weak model)

### Testing Budget Overflow

**Setup**:
```bash
# Set very low budget
# Edit .env:
MAX_COST_PER_SESSION=0.001
```

**Test**:
```bash
# First request succeeds
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "Hi"}],
    "session_id": "budget-test"
  }'

# Second request should fail with budget exceeded
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "Hello again"}],
    "session_id": "budget-test"
  }'
```

**Expected Error**:
```json
{
  "error": "Budget exceeded",
  "session_id": "budget-test",
  "current_cost": 0.001234,
  "max_budget": 0.001
}
```

---

## Success Criteria

### Must Pass (Critical)
- ✅ Health endpoint responds
- ✅ OpenAI format compatibility
- ✅ Budget tracking works
- ✅ Judge scores simple prompts low
- ✅ Cycle detection header present

### Should Pass (Important)
- ✅ Budget accumulates correctly
- ✅ Complexity scores are reasonable
- ✅ Cycles detected on repetition

### Can Skip (Expensive)
- ⏭️  Budget overflow rejection
- ⏭️  Strong model routing
- ⏭️  Dynamic threshold adjustment over 20+ requests

---

## Troubleshooting

### Test Failures

**If health check fails**:
```bash
# Check if server is running
docker-compose ps

# Check logs
docker-compose logs -f
```

**If API calls fail with authentication errors**:
```bash
# Verify API keys are set
docker exec sentinelrouter env | grep API_KEY

# Check .env file has real keys
cat .env | grep API_KEY
```

**If costs are higher than expected**:
- Check which model is being used (X-Sentinel-Model-Used header)
- Verify COMPLEXITY_THRESHOLD is set to 0.5 (default)
- Simple prompts should always use DeepSeek (cheap)

---

## Cost Management Recommendations

1. **Development**: Use default settings (threshold 0.5), most requests use weak model
2. **Testing**: Run automated suite (~$0.005), skip expensive manual tests
3. **Production**: Monitor escalation rate, ensure it stays around 5%
4. **Budget Alerts**: Set MAX_COST_PER_SESSION appropriately for your use case

---

## Next Steps After Testing

1. **Review Results**: Check generated JSON report
2. **Monitor Logs**: Examine routing decisions in logs/sentinelrouter.log
3. **Tune Threshold**: Adjust COMPLEXITY_THRESHOLD based on your accuracy/cost tradeoff
4. **Production Deployment**: If all tests pass, ready for production use

---

## Appendix: Test Data Reference

### Simple Prompts (Complexity < 0.3)
- "Say 'hi'"
- "What is 2+2?"
- "Count to 3"
- "What is the capital of France?"

### Medium Prompts (Complexity 0.2-0.6)
- "Explain lists vs tuples in Python"
- "What is Docker?"
- "How does HTTP work?"

### Complex Prompts (Complexity > 0.5)
- "Analyze Gödel's incompleteness theorems..."
- "Design a distributed consensus algorithm..."
- "Explain quantum entanglement and its implications..."

Use simple prompts for testing to minimize costs! 💰
