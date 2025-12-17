# Scripts Directory

Utility scripts for SentinelRouter maintenance and testing.

## Migration Scripts

### `migrate_enhanced_tracking.py`
**Purpose:** Add enhanced routing decision tracking to existing databases

**What it does:**
- Adds token tracking columns to `routing_decisions` table (input_tokens, output_tokens, total_tokens)
- Adds latency tracking columns (request_latency_ms, model_latency_ms, judge_latency_ms)
- Creates new `escalation_traces` table for detailed strong model escalation tracking
- Creates indexes for performance

**Usage:**
```bash
python3 scripts/migrate_enhanced_tracking.py
```

**Safe to run multiple times** - checks if columns/tables exist before adding.

**Documentation:** See `documentation/internal/enhanced-tracking-implementation.md`

---

## Testing & Verification Scripts

### `check_rate_limiter_state.py`
**Purpose:** Check current state of the rate limiter after making requests

**Usage:**
```bash
python3 scripts/check_rate_limiter_state.py
```

**Output:**
- Requests and tokens used in the last minute
- Requests and tokens used in the last day
- Confirms whether rate limiter is recording usage

**When to use:**
- Verifying rate limiter after system changes
- Debugging unexpected rate limit behavior
- Checking usage after test requests

---

### `verify_rate_limiter.py`
**Purpose:** Comprehensive rate limiter functionality verification

**Usage:**
```bash
python3 scripts/verify_rate_limiter.py
```

**Tests:**
1. Records multiple requests and verifies usage tracking
2. Checks that limits are enforced correctly
3. Verifies preemptive blocking works as expected

**When to use:**
- After changes to rate limiting logic
- After database migrations
- Troubleshooting rate limit enforcement issues

---

## Quick Reference

All scripts can be run directly:

```bash
# Make scripts executable (first time only)
chmod +x scripts/*.py

# Run any script
./scripts/migrate_enhanced_tracking.py
./scripts/check_rate_limiter_state.py
./scripts/verify_rate_limiter.py
```

Or with Python:

```bash
python3 scripts/<script_name>.py
```

## Documentation

For detailed documentation about scripts and testing:
- **Testing Guide:** `documentation/development/testing.md`
- **Monitoring Guide:** `documentation/operations/monitoring.md`
- **Implementation Details:** `documentation/internal/`
