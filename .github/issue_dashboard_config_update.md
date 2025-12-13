I'll create a comprehensive GitHub issue document for the dashboard config update functionality based on the principal engineer review findings.


# Dashboard Configuration Update - Critical Integration Issues**Priority**: 🔴 **CRITICAL**  **Status**: Open  **Assignee**: TBD  **Estimated Effort**: 2-3 days  **Labels**: `bug`, `feature`, `critical`, `dashboard`, `configuration`---## 📋 OverviewThe dashboard configuration CRUD functionality has been implemented with new schemas, StateManager methods, and API endpoints. However, **critical integration gaps** prevent the new configuration system from actually affecting the router's behavior. Dashboard changes are stored but not used by the routing logic.**Current State**: Configuration can be modified via dashboard, but changes have **NO EFFECT** on actual routing behavior.**Required State**: Dashboard configuration changes must be immediately reflected in routing decisions, budget calculations, rate limiting, and judge behavior.---## 🔴 Critical Issues (Must Fix)### Issue #1: Router Ignores New Routing Order Config**Location**: [`sentinelrouter/sentinelrouter/router_logic.py`](sentinelrouter/sentinelrouter/router_logic.py) lines 140-160**Problem**:- Router uses hardcoded environment variables for model selection:  ```python  if chosen_tier == "strong_tier":      model_id = "claude-opus-4-5-20251101"  # ❌ From STRONG_MODEL_ID env var  else:      model_id = "deepseek-reasoner"  # ❌ From WEAK_MODEL_ID env var
New schema has RoutingOrderConfig with strong_models and weak_models lists
Dashboard allows changing model order
Changes are ignored by router
Expected Behavior:


routing_order = self.state_manager.get_routing_order_config()if chosen_tier == "strong_tier":    for model_id in routing_order.strong_models:        if self.state_manager.is_model_available(model_id):            breakelse:    for model_id in routing_order.weak_models:        if self.state_manager.is_model_available(model_id):            break
Test Required:


async def test_routing_order_config_affects_routing():    # Change routing order: put model-B before model-A    await update_routing_order(weak_models=["model-B", "model-A"])        # Make routing request    result = await router.route(session_id, prompt, messages)        # Verify model-B was selected (not model-A)    assert result["model_id"] == "model-B"
User Impact: Admin changes routing order in dashboard → Nothing happens → Frustrated admin thinks system is broken.

Issue #2: Judge Ignores Judge Config
Location: judge.py lines 45-60

Problem:

Judge has hardcoded model list:

self.models = [    "gemini-2.5-flash-lite-judge",    "deepseek-judge-backup1",]
New schema has JudgeConfig with model_order and is_judge_required fields
Dashboard allows configuring judge models and disabling judge
Judge ignores this configuration
Expected Behavior:


class StingyJudge:    def __init__(self, state_manager):        self.state_manager = state_manager        async def judge(self, prompt: str):        judge_config = self.state_manager.get_judge_config()                # Honor isJudgeRequired flag (addresses GitHub Issue #1)        if not judge_config.is_judge_required:            return 0.0, "LOW", "Judge disabled by config"                # Use model_order from config        for model_id in judge_config.model_order:            try:                return await self._call_judge_model(model_id, prompt)            except Exception:                continue  # Try next judge model
Test Required:


async def test_judge_config_disable():    # Disable judge in config    await update_judge_config(is_judge_required=False)        # Make routing request    result = await router.route(session_id, prompt, messages)        # Verify judge was NOT called (check logs)    assert "Judge disabled by config" in result["reason"]
User Impact:

Admin disables judge to save latency/cost → Judge still runs → Wasted money
Admin changes judge model order → Order ignored → Wrong judge model used
Issue #3: Budget Calculation Ignores New Cost Structure
Location: budget.py lines 75-90

Problem:

Budget calculation uses hardcoded pricing rates
VERIFICATION_REPORT.md shows: $0.000026 per simple request (hardcoded calculation)
New schema has CostInfo with per_call, per_token_input, per_token_output fields
Dashboard allows setting custom pricing per model
Budget calculation doesn't use it
Expected Behavior:


def calculate_cost(self, model_id: str, input_tokens: int, output_tokens: int):    model_config = self.state_manager.config.models[model_id]        cost = model_config.cost.per_call    cost += input_tokens * model_config.cost.per_token_input    cost += output_tokens * model_config.cost.per_token_output        return cost
Test Required:


async def test_budget_uses_custom_cost():    # Set custom pricing for test model    await update_model_config("test-model", {        "cost": {            "per_call": 0.01,            "per_token_input": 0.0001,            "per_token_output": 0.0002        }    })        # Make request with 100 input tokens, 50 output tokens    result = await router.route(session_id, prompt, messages)        # Verify cost = 0.01 + (100 * 0.0001) + (50 * 0.0002) = 0.03    assert result["cost"] == 0.03
User Impact:

Admin sets different pricing for premium models → Budget tracks wrong cost → Financial loss
Can't charge clients accurately for different model tiers
Issue #4: Rate Limiting Uses Old Schema
Location: router_logic.py lines 200-210

Problem:

Rate limiter reads from old model.limits.requests_per_minute field
New schema has separate free_tier_limits and paid_tier_limits
Dashboard allows setting different limits for free vs paid users
Rate limiter doesn't distinguish between tiers
Expected Behavior:


# Determine user's tier (free vs paid)user_tier = self._get_user_tier(session_id)if user_tier == "free":    limits = model.free_tier_limitselse:    limits = model.paid_tier_limits# Check all limit typesif requests_today >= limits.requests_per_day:    raise RateLimitError("Daily request limit exceeded")if requests_this_minute >= limits.requests_per_minute:    raise RateLimitError("Rate limit exceeded")if tokens_today >= limits.tokens_per_day:    raise RateLimitError("Daily token limit exceeded")if tokens_this_minute >= limits.tokens_per_minute:    raise RateLimitError("Token rate limit exceeded")
Test Required:


async def test_free_tier_rate_limits():    # Set free tier limit to 10 RPM, paid tier to 100 RPM    await update_model_config("test-model", {        "free_tier_limits": {"requests_per_minute": 10},        "paid_tier_limits": {"requests_per_minute": 100}    })        # Free user makes 11th request in same minute    with pytest.raises(RateLimitError):        await router.route(free_user_session, prompt, messages)        # Paid user can make 11th request    result = await router.route(paid_user_session, prompt, messages)    assert result["status"] == "success"
User Impact:

Free users bypass intended rate limits → System overload
Paid users hit free tier limits → Angry customers
Issue #5: Model Deletion Instead of Soft Delete
Location: state_manager.py lines 162-167

Problem:

delete_model() permanently removes model from config:

del self.config.models[model_id]  # ❌ Hard delete
Historical routing_decisions logs reference deleted model IDs
Dashboard log viewer tries to display old routing decisions → crashes with KeyError
Requirement: Models should be marked inactive, not deleted
Expected Behavior:


async def delete_model(self, model_id: str):    """Mark model as inactive (soft delete) to preserve historical logs."""    if model_id not in self.config.models:        raise ValueError(f"Model {model_id} not found")        # Soft delete: mark as inactive instead of removing    self.config.models[model_id].status = "BANNED"    self.config.models[model_id].status_valid_till = None  # Permanent ban    self._mark_dirty()        logger.info(f"Soft-deleted model {model_id} (marked as BANNED)")
Test Required:


async def test_soft_delete_preserves_logs():    # Make routing request with model-A    result = await router.route(session_id, prompt, messages)    assert result["model_id"] == "model-A"        # Delete model-A via dashboard    await state_manager.delete_model("model-A")        # Verify model-A still exists but is BANNED    model = state_manager.config.models["model-A"]    assert model.status == "BANNED"        # Verify dashboard can still display historical logs    logs = await get_routing_logs()    assert logs[0]["model_id"] == "model-A"  # Should not crash        # Verify new requests don't use model-A    result = await router.route(session_id, prompt, messages)    assert result["model_id"] != "model-A"
User Impact:

Admin deletes old model → Dashboard crashes when viewing history
Logs show model_id: "deleted_model_123" with no details
🟠 Major Issues (High Priority)
Issue #6: statusValidTill Not Enforced
Problem: Models with status: BANNED and expired status_valid_till should auto-unban, but router doesn't check.

Fix:


if model.status == "BANNED":    if model.status_valid_till and datetime.now() < model.status_valid_till:        continue  # Still banned    else:        # Auto-unban expired bans        await self.state_manager.unban_model(model_id)
Issue #7: Inconsistent Status Enum
Problem: Schema uses "active", "inactive", "paused" but requirement specifies "ACTIVE", "BANNED".

Fix: Change schema to match requirement:


status: Literal["ACTIVE", "BANNED"] = "ACTIVE"
Issue #8: No Error Handling in Dashboard APIs
Problem: API endpoints don't catch exceptions, returning generic 500 errors instead of helpful messages.

Fix: Wrap all API endpoints in try/except:


@app.post("/api/dashboard/models")async def add_model_endpoint(model_id: str, config: ModelConfig):    try:        await state_manager.add_model(model_id, config)        return {"status": "success"}    except ValueError as e:        raise HTTPException(status_code=400, detail=str(e))    except Exception as e:        logger.error(f"Failed to add model: {e}")        raise HTTPException(status_code=500, detail="Internal server error")
Issue #9: No Rollback on Partial Update Failure
Problem: If validation fails mid-update, state is left corrupted.

Fix: Validate on a copy first, then apply atomically:


async def update_model_config(self, model_id: str, updates: Dict[str, Any]):    model = self.config.models[model_id]    temp_model = model.copy(deep=True)        for key, value in updates.items():        setattr(temp_model, key, value)        temp_model.model_validate(temp_model)  # Validate copy    self.config.models[model_id] = temp_model  # Apply if valid    self._mark_dirty()
🟡 Minor Issues
Issue #10: API Keys Logged in Plain Text
Fix: Mask sensitive fields before logging:


def mask_key(key: str) -> str:    return f"{key[:4]}...{key[-4:]}" if len(key) >= 8 else "***"
Issue #11: Incomplete Migration Script
Fix: Add proper defaults for nested structures in migration script.

Issue #12: model_key Validation Missing
Fix: Add validation:


model_key: str = Field(..., min_length=10)
📊 Test Coverage Requirements
Integration Tests Needed:
test_routing_order_affects_routing: Verify routing order config is used
test_judge_config_disable: Verify is_judge_required: false skips judge
test_budget_uses_custom_cost: Verify custom pricing is used
test_free_tier_rate_limits: Verify tier limits are enforced
test_soft_delete_preserves_logs: Verify soft delete keeps historical data
Current Test Status:
✅ 108/116 tests passing (93%)
✅ Schema validation tests pass
✅ StateManager CRUD methods work in isolation
❌ No integration tests for config → routing flow
❌ No tests verifying dashboard changes affect behavior
📋 Acceptance Criteria
 Changing routing order in dashboard affects next routing decision
 Setting is_judge_required: false skips judge call
 Custom pricing in dashboard is used for budget calculation
 Free tier users hit lower rate limits than paid users
 Deleting model preserves historical logs
 Banned models with expired status_valid_till auto-unban
 Dashboard APIs return helpful error messages
 All 5 integration tests pass
 108+ unit tests still pass (no regressions)
🚀 Implementation Plan
Phase 1: Critical Fixes (Day 1)
 Fix router to use routing_order_config (2 hours)
 Fix judge to use judge_config (2 hours)
 Fix budget to use new cost structure (1 hour)
 Fix rate limits to use tier limits (1 hour)
 Change delete to soft delete (30 mins)
Phase 2: Major Fixes (Day 2)
 Enforce status_valid_till (30 mins)
 Fix status enum to ACTIVE|BANNED (15 mins)
 Add error handling to APIs (1 hour)
 Add rollback on validation failure (1 hour)
Phase 3: Testing (Day 2-3)
 Add 5 integration tests (4 hours)
 Verify 108+ tests still pass (1 hour)
 Manual testing of dashboard → routing flow (2 hours)
Total Estimated Time: 2-3 days

🔗 Related Issues
GitHub Issue #1: Judge Mode Optimization (addresses isJudgeRequired flag)
GitHub Issue #2: Semantic-Hash Request/Response Cache
VERIFICATION_REPORT.md: Shows current working state (108 tests passing)
📝 Notes
What's Already Working:
✅ Schema definitions are solid
✅ StateManager CRUD methods exist
✅ Dashboard API endpoints are well-structured
✅ Core routing logic works (108 tests passing)
✅ DeepSeek + Anthropic integration verified
What Needs Fixing:
❌ Router doesn't USE new routing order
❌ Judge doesn't USE judge config
❌ Budget doesn't USE new cost structure
❌ Rate limiter doesn't USE tier limits
❌ Delete doesn't soft-delete
Root Cause: New configuration schema was added but not integrated into the business logic. The data storage layer is complete, but the consumption layer still uses old hardcoded values.

💬 Discussion
Why is this critical?

Users can modify configuration via dashboard, but changes have zero effect on system behavior
This creates a false sense of control and erodes trust in the system
Financial impact: Wrong pricing/rate limits can cause revenue loss
Why wasn't this caught in testing?

Tests only verify StateManager methods in isolation
No integration tests for config → routing flow
Manual testing didn't verify dashboard changes affect routing
What's the fix complexity?

Medium - Requires updating multiple modules (router, judge, budget, rate limiter)
But changes are straightforward: replace hardcoded values with config lookups
Estimated 2-3 days for experienced developer
🎯 Success Metrics
 Dashboard model order change → Next request uses new order
 Dashboard judge disable → Judge not called (latency drops by ~2 seconds)
 Dashboard pricing change → Budget reflects new cost (verified in logs)
 Free user → Hits lower rate limit (paid user doesn't)
 Model delete → Historical logs still render correctly
Last Updated: December 12, 2025
Created By: Principal Engineer Review
Severity: 🔴 Critical - Blocks dashboard functionality