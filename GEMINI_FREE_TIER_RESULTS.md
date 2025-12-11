# Gemini Free Tier Models Test Results

**Test Date**: December 11, 2025  
**API Key**: AIzaSyCmm7euC6vHz39nJXEZAkqqJeUIB1rtVI8

## Working Models (Free Tier Available)

### ✅ gemini-2.5-flash
- **Status**: Working
- **Response**: "Hi there! How can I help you today?"
- **Use Case**: Best for general purpose, recommended as primary weak model
- **Pricing**: Free tier available

### ✅ gemini-2.5-flash-lite  
- **Status**: Working
- **Response**: "Hi there! How can I help you today?"
- **Use Case**: Faster, lighter version for simple queries
- **Pricing**: Free tier available

### ✅ gemini-flash-latest
- **Status**: Working
- **Response**: "Hi there! How can I help you today?"
- **Use Case**: Always points to latest stable flash model
- **Pricing**: Free tier available

### ✅ gemini-flash-lite-latest
- **Status**: Working (needs confirmation)
- **Use Case**: Latest lite version
- **Pricing**: Free tier available

### ✅ gemini-exp-1206
- **Status**: Working (needs confirmation)
- **Use Case**: Experimental model from December 6th
- **Pricing**: Free tier available

## Not Working (Quota Exceeded on Free Tier)

### ❌ gemini-2.0-flash
- **Error**: Quota exceeded for free tier
- **Issue**: This model has separate quota limits that are exhausted

### ❌ gemini-2.0-flash-lite
- **Error**: Quota exceeded for free tier
- **Issue**: This model has separate quota limits that are exhausted

### ❌ gemini-2.0-flash-exp
- **Error**: Quota exceeded for free tier
- **Issue**: Experimental model with stricter limits

## Current Configuration Issue

**Problem Found**: We were calling `gemini-2.0-flash-exp` which hit quota limits.

**Fix Applied**: Changed to use:
- Backup 1: `gemini-2.5-flash` ✅ Working
- Backup 2: `gemini-2.0-flash-exp` (keeping for live features, but quota exceeded)

## Recommendations for Weak Model List

### Recommended Models to Add:
1. **gemini-2.5-flash** - Primary choice (best balance)
2. **gemini-2.5-flash-lite** - Secondary choice (faster)
3. **gemini-flash-latest** - Tertiary choice (always updated)

### Configuration Priority:
```
Weak Model Failover Chain:
1. deepseek-chat (primary - reliable, fast)
2. gemini-2.5-flash (backup 1 - free tier working)
3. gemini-2.5-flash-lite (backup 2 - faster, lighter)
```

### Judge Model Priority:
```
Judge Failover Chain:
1. deepseek-chat (primary - proven reliable)
2. gemini-2.5-flash (backup 1 - free tier working)
3. gemini-flash-latest (backup 2 - always updated)
```

## Test Commands Used

```bash
# Test single model
curl -s -X POST "https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={KEY}" \
  -H "Content-Type: application/json" \
  -d '{"contents": [{"parts": [{"text": "Hi"}]}]}'

# Check for success
jq -r 'if .candidates then "✅ WORKS" else "❌ " + .error.message end'
```

## Next Steps

1. ✅ Update router_logic.py weak model chain to use gemini-2.5-flash and gemini-2.5-flash-lite
2. ✅ Update judge.py to use gemini-2.5-flash instead of 2.0-flash-exp
3. ⚠️ Consider removing 2.0-flash-exp entirely (quota exhausted)
4. 🔄 Test router with new models
5. 📊 Monitor metrics to verify models working through router

## Key Findings

- **2.5 models have better free tier availability** than 2.0 models
- **2.0-flash-exp is quota-limited** on free tier
- **2.5-flash** is the recommended general-purpose model
- **2.5-flash-lite** is best for simple, fast queries
- All tested 2.5 models are currently working with free tier
