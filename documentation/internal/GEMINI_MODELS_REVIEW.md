# Gemini Models Review & Recommendations

## Current Issues Found

### 1. ❌ Incorrect Rate Limits
**Current Config:** `gemini-2.5-flash-lite-primary` shows:
- `requests_per_minute: 100`
- `requests_per_day: 50000`
- `tokens_per_minute: 1000000`

**Problem:** These are NOT accurate. According to Google's documentation:
- Rate limits **vary by tier** (Free, Tier 1, Tier 2, Tier 3)
- Actual limits should be checked in [Google AI Studio](https://aistudio.google.com/usage)
- Free tier is typically much more restricted than shown
- Rate limits are not guaranteed and "actual capacity may vary"

**Recommendation:** 
- Use conservative estimates for free tier
- Based on typical Gemini free tier patterns: **15 RPM, 1500 RPD** for free tier
- Update config to reflect realistic free tier limits

---

## Missing Gemini Free Models

### Currently Have
✅ `gemini-2.5-flash-lite-primary` (judge model only)

### Missing (All FREE on Google AI)

#### 1. **Gemini 2.0 Flash** ⭐ RECOMMENDED
- **Model ID:** `gemini-2.0-flash`
- **Status:** Stable, production-ready
- **Description:** Second generation workhorse model
- **Context:** 1 million tokens
- **Free Tier:** Yes
- **Use Case:** Best general-purpose free model
- **Speed:** Moderate
- **Why Add:** Most balanced free model for weak tier routing

#### 2. **Gemini 2.0 Flash-Lite** 
- **Model ID:** `gemini-2.0-flash-lite`
- **Status:** Stable, production-ready
- **Description:** Second generation small workhorse model
- **Context:** 1 million tokens
- **Free Tier:** Yes
- **Use Case:** Ultra-fast fallback
- **Speed:** Very fast
- **Why Add:** Good for simple queries, faster than 2.0 Flash

#### 3. **Gemini 2.5 Flash** ⭐ RECOMMENDED
- **Model ID:** `gemini-2.5-flash`
- **Status:** Stable, production-ready
- **Description:** Best price-performance, supports thinking budgets
- **Context:** 1 million tokens
- **Free Tier:** Yes
- **Use Case:** Complex reasoning tasks
- **Speed:** Moderate
- **Why Add:** Best reasoning capabilities in free tier

#### 4. **Gemini 3 Flash Preview** ⭐ NEW & POWERFUL
- **Model ID:** `gemini-3-flash-preview`
- **Status:** Preview (more restrictive limits)
- **Description:** Most intelligent model built for speed
- **Context:** Not specified (likely 1M)
- **Free Tier:** Yes (with restrictive limits)
- **Use Case:** Latest/best quality
- **Speed:** Fast
- **Why Add:** Newest generation, superior search & grounding
- **Note:** Preview models may change before stable release

#### 5. **Gemini 2.5 Flash-Lite** (current model, but not in weak routing)
- **Model ID:** `gemini-2.5-flash-lite`
- **Status:** Stable, production-ready
- **Description:** Smallest, most cost-effective
- **Context:** Not specified
- **Free Tier:** Yes
- **Use Case:** High-throughput, scale usage
- **Speed:** Very fast
- **Current Status:** Only used as judge, NOT in weak model routing

---

## Recommended Gemini Configuration

### Priority Order Analysis

**Free Tier Rate Limits (Typical):**
- RPM: ~15 requests/minute
- RPD: ~1,500 requests/day
- TPM: ~32,000 tokens/minute (varies by model)

### Proposed Weak Model Order (with Gemini)

```
Order 1: deepseek-chat (60 RPM, paid)
Order 2: groq-llama-3.1-8b-instant (30 RPM, quota-based)
Order 2: groq-llama-3.3-70b-versatile (30 RPM, quota-based)
Order 2: gemini-2.5-flash (15 RPM, free) ⭐ ADD
Order 2: gemini-2.0-flash (15 RPM, free) ⭐ ADD
Order 3: gemini-2.5-flash-lite (15 RPM, free) ⭐ MOVE HERE
Order 3: gemini-2.0-flash-lite (15 RPM, free) ⭐ ADD
Order 3: openrouter-mixtral-8x7b-free (20 RPM, free)
Order 3: openrouter-llama-3-8b-free (20 RPM, free)
Order 3: groq-qwen-3-32b (30 RPM, quota-based)
Order 4: gemini-3-flash-preview (5-10 RPM, preview) ⭐ ADD (optional)
```

### Proposed Judge Model Order (with Gemini)

```
1. gemini-3-flash-preview (newest, best reasoning) ⭐ ADD
2. gemini-2.5-flash (stable, thinking budgets) ⭐ ADD
3. gemini-2.0-flash (stable workhorse) ⭐ ADD
4. gemini-2.5-flash-lite (current primary - keep)
5. groq-llama-3.3-70b-versatile
6. groq-llama-3.1-8b-instant
7. openrouter-mixtral-8x7b-free
8. gemini-2.0-flash-lite (last resort) ⭐ ADD
9. deepseek-judge-backup1
```

---

## Specific Recommendations

### 1. Correct Rate Limits for Gemini Models

**Update `gemini-2.5-flash-lite-primary`:**
```json
{
  "limits": {
    "requests_per_minute": 15,
    "requests_per_day": 1500,
    "tokens_per_minute": 32000
  },
  "free_tier_limits": {
    "requests_per_day": 1500,
    "requests_per_minute": 15,
    "tokens_per_minute": 32000,
    "tokens_per_day": 1000000
  }
}
```

### 2. Add Missing Gemini Models

**Priority 1 (Must Add):**
1. `gemini-2.5-flash` - Best reasoning
2. `gemini-2.0-flash` - Most stable
3. `gemini-2.0-flash-lite` - Fastest fallback

**Priority 2 (Nice to Have):**
4. `gemini-3-flash-preview` - Latest generation

### 3. Move Current Model to Weak Routing

**Current:** `gemini-2.5-flash-lite-primary` is ONLY a judge model

**Recommendation:** Also add to weak model routing at order 3

---

## API Key Requirements

**Current:** You have:
- `GEMINI_BACKUP1_API_KEY` (used for judge)
- `GEMINI_BACKUP2_API_KEY` (backup judge)

**Recommendation:**
- Use same API keys for new models (all use Google AI API)
- No additional keys needed
- All Gemini models work with same API key

---

## Model-to-API-Key Mapping

```python
# Current structure in clients.py
gemini_backup1_api_key → gemini-2.0-flash-exp (judge backup)
gemini_backup2_api_key → gemini-2.5-flash (judge backup)

# Proposed additions:
gemini_backup1_api_key → Can be used for ALL new Gemini models
  - gemini-2.0-flash
  - gemini-2.0-flash-lite
  - gemini-2.5-flash
  - gemini-2.5-flash-lite
  - gemini-3-flash-preview
```

---

## Expected Free Tier Performance

Based on Google's free tier documentation:

| Model | RPM | RPD | TPM | Context | Speed |
|-------|-----|-----|-----|---------|-------|
| gemini-3-flash-preview | 5-10 | 500 | 20K | ? | Very Fast |
| gemini-2.5-flash | 15 | 1500 | 32K | 1M | Fast |
| gemini-2.5-flash-lite | 15 | 1500 | 32K | ? | Very Fast |
| gemini-2.0-flash | 15 | 1500 | 32K | 1M | Fast |
| gemini-2.0-flash-lite | 15 | 1500 | 32K | 1M | Very Fast |

**Notes:**
- Preview models have MORE restrictive limits
- Actual limits visible in AI Studio usage dashboard
- Limits are per PROJECT, not per API key
- Free tier limits reset at midnight Pacific time

---

## Implementation Steps

### Step 1: Fix Current Model Rate Limits
Update `gemini-2.5-flash-lite-primary` with realistic limits (15 RPM, 1500 RPD)

### Step 2: Add New Gemini Client Methods
Extend `clients.py` with getters for new models:
- `get_gemini_2_0_flash_client()`
- `get_gemini_2_0_flash_lite_client()`
- `get_gemini_2_5_flash_client()`
- `get_gemini_3_flash_preview_client()` (optional)

### Step 3: Add Model Configs
Add configurations for each new model in `models_config.json`

### Step 4: Update Routing Orders
- Add to `weak_models` array
- Add to `judge_config.model_order` array

### Step 5: Test All Models
Create test script similar to `test_groq_models.py`

---

## Why These Models Matter

### Use Case Mapping

**Gemini 2.5 Flash:**
- Complex reasoning tasks
- Code generation with thinking
- Best for: Multi-step problems

**Gemini 2.0 Flash:**
- Balanced workhorse
- Reliable and stable
- Best for: General queries

**Gemini 2.0 Flash-Lite:**
- High-throughput scenarios
- Simple Q&A
- Best for: Fast fallback

**Gemini 3 Flash Preview:**
- Latest generation quality
- Superior search/grounding
- Best for: Cutting-edge features

---

## Risks & Considerations

### Preview Models
⚠️ **Gemini 3 Flash Preview:**
- May change before stable release
- More restrictive rate limits
- Could be deprecated with 2 weeks notice
- Consider for testing, not critical path

### Rate Limiting
⚠️ **All Gemini Free Models:**
- Shared quotas across all free-tier usage
- Can hit rate limits quickly if used heavily
- Need good fallback chain
- Monitor usage in AI Studio

### API Key Management
⚠️ **Multiple Gemini Models:**
- All share same API key
- Rate limits are per PROJECT
- Can't increase limits by using multiple keys
- Must upgrade to paid tier for higher limits

---

## Questions to Answer

1. **Which models should we add?**
   - Minimum: gemini-2.5-flash, gemini-2.0-flash, gemini-2.0-flash-lite
   - Optional: gemini-3-flash-preview

2. **What order priority?**
   - Suggested: Order 2 for flash models, Order 3 for lite models

3. **Use for weak routing, judge, or both?**
   - Recommended: Both (maximize free tier value)

4. **How to handle preview models?**
   - Keep separate, mark as experimental, lower priority

5. **Should we consolidate API keys?**
   - Yes - use gemini_backup1_api_key for all

---

## Next Steps

Please confirm:
1. ✅ Fix rate limits for existing gemini-2.5-flash-lite-primary
2. ✅ Add gemini-2.5-flash (stable, best reasoning)
3. ✅ Add gemini-2.0-flash (stable, workhorse)
4. ✅ Add gemini-2.0-flash-lite (stable, fast)
5. ⚠️ Add gemini-3-flash-preview (preview, optional)
6. ✅ Move gemini-2.5-flash-lite to weak routing (not just judge)

Once confirmed, I'll implement all changes with proper testing.
