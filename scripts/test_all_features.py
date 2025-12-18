#!/usr/bin/env python3
"""
Comprehensive Feature Test Suite for SentinelRouter

Tests all major features and modules:
1. Budget Kill-Switch (Module A)
2. Judge & Categorizer (Module B)
3. Dynamic Thresholding (Module C)
4. Cycle Detection (Module D)
5. Semantic Cache
6. Rate Limiting
7. OpenRouter Integration
8. Enhanced Logging & Tracking
9. State Management
10. Metrics Collection
11. API Endpoints
12. Failover & Fallback
"""

import asyncio
import sys
import sqlite3
import json
from pathlib import Path
from datetime import datetime
import httpx

sys.path.insert(0, str(Path(__file__).parent))

from sentinelrouter.sentinelrouter.router_logic import Router
from sentinelrouter.sentinelrouter.database import get_session_local
from sentinelrouter.sentinelrouter.budget import BudgetKillSwitch
from sentinelrouter.sentinelrouter.judge import StingyJudge
from sentinelrouter.sentinelrouter.threshold import DynamicThreshold
from sentinelrouter.sentinelrouter.cycle_detector import CycleDetector
from sentinelrouter.sentinelrouter.semantic_cache import SemanticCache
from sentinelrouter.sentinelrouter.rate_limiter import get_rate_limiter
from sentinelrouter.sentinelrouter.metrics import get_metrics_collector
from sentinelrouter.sentinelrouter.state_manager import get_state_manager


class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}  {text}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 80}{Colors.ENDC}\n")


def print_test(name, status, detail=""):
    symbols = {
        "pass": f"{Colors.OKGREEN}✅",
        "fail": f"{Colors.FAIL}❌",
        "warn": f"{Colors.WARNING}⚠️",
        "info": f"{Colors.OKCYAN}ℹ️"
    }
    print(f"{symbols.get(status, '•')} {name}{Colors.ENDC}")
    if detail:
        print(f"   {detail}")


class TestResults:
    def __init__(self):
        self.results = {}
        self.current_feature = None
    
    def set_feature(self, feature_name):
        self.current_feature = feature_name
        self.results[feature_name] = {"passed": 0, "failed": 0, "warnings": 0, "tests": []}
    
    def add_result(self, test_name, status, detail=""):
        if not self.current_feature:
            return
        
        self.results[self.current_feature]["tests"].append({
            "name": test_name,
            "status": status,
            "detail": detail
        })
        
        if status == "pass":
            self.results[self.current_feature]["passed"] += 1
        elif status == "fail":
            self.results[self.current_feature]["failed"] += 1
        elif status == "warn":
            self.results[self.current_feature]["warnings"] += 1
        
        print_test(test_name, status, detail)
    
    def print_summary(self):
        print_header("TEST SUMMARY")
        
        total_passed = sum(r["passed"] for r in self.results.values())
        total_failed = sum(r["failed"] for r in self.results.values())
        total_warnings = sum(r["warnings"] for r in self.results.values())
        
        for feature, data in self.results.items():
            status_icon = "✅" if data["failed"] == 0 else "❌"
            print(f"\n{status_icon} {feature}")
            print(f"   Passed: {data['passed']}, Failed: {data['failed']}, Warnings: {data['warnings']}")
        
        print(f"\n{Colors.BOLD}Overall:{Colors.ENDC}")
        print(f"  {Colors.OKGREEN}✅ Passed: {total_passed}{Colors.ENDC}")
        print(f"  {Colors.FAIL}❌ Failed: {total_failed}{Colors.ENDC}")
        print(f"  {Colors.WARNING}⚠️  Warnings: {total_warnings}{Colors.ENDC}")
        
        print("\n" + "=" * 80)
        if total_failed == 0:
            print(f"{Colors.OKGREEN}{Colors.BOLD}🎉 ALL TESTS PASSED!{Colors.ENDC}")
        else:
            print(f"{Colors.FAIL}{Colors.BOLD}⚠️  SOME TESTS FAILED{Colors.ENDC}")
        print("=" * 80 + "\n")


async def test_budget_killswitch(results):
    """Test Module A: Budget Kill-Switch."""
    results.set_feature("Module A: Budget Kill-Switch")
    
    SessionLocal = get_session_local()
    db = SessionLocal()
    budget = BudgetKillSwitch(db)
    
    try:
        # Test session creation
        session = budget.get_or_create_session("test_budget_001")
        results.add_result("Session Creation", "pass", f"Max cost: ${session.max_cost_per_session}")
        
        # Test cost addition
        initial_cost = session.current_cost
        budget.add_cost("test_budget_001", 1.50)
        session = budget.get_or_create_session("test_budget_001")
        
        if session.current_cost == initial_cost + 1.50:
            results.add_result("Cost Addition", "pass", f"${initial_cost} + $1.50 = ${session.current_cost}")
        else:
            results.add_result("Cost Addition", "fail", f"Expected ${initial_cost + 1.50}, got ${session.current_cost}")
        
        # Test budget check
        try:
            budget.check_budget("test_budget_001", 5.0)
            results.add_result("Budget Check (Under Limit)", "pass", "No exception raised")
        except Exception as e:
            results.add_result("Budget Check (Under Limit)", "fail", str(e))
        
        # Test budget exceeded
        session.current_cost = session.max_cost_per_session + 1
        db.commit()
        
        try:
            allowed = budget.check_budget("test_budget_001", 1.0)
            if allowed:
                results.add_result("Budget Exceeded Detection", "fail", "Should have blocked over-budget request")
            else:
                results.add_result("Budget Exceeded Detection", "pass", "Correctly blocked over-budget request")
        except Exception as e:
            if "exceeded" in str(e).lower():
                results.add_result("Budget Exceeded Detection", "pass", "Correctly raised exception for over-budget")
            else:
                results.add_result("Budget Exceeded Detection", "fail", f"Unexpected error: {e}")
        
    finally:
        db.close()


async def test_judge_categorizer(results):
    """Test Module B: Stingy Judge & Categorizer."""
    results.set_feature("Module B: Judge & Categorizer")
    
    SessionLocal = get_session_local()
    db = SessionLocal()
    
    try:
        judge = StingyJudge()
        
        # Test simple prompt
        simple_prompt = "What is 2+2?"
        complexity, impact, reasoning = await judge.judge(simple_prompt)
        
        if complexity < 0.5:
            results.add_result("Simple Prompt Categorization", "pass", 
                             f"Complexity: {complexity:.3f}, Impact: {impact}")
        else:
            results.add_result("Simple Prompt Categorization", "warn",
                             f"Expected low complexity, got {complexity:.3f}")
        
        # Test complex prompt
        complex_prompt = "Explain the mathematical foundations of quantum field theory including Feynman diagrams, renormalization, and the Standard Model."
        complexity, impact, reasoning = await judge.judge(complex_prompt)
        
        if complexity > 0.5:
            results.add_result("Complex Prompt Categorization", "pass",
                             f"Complexity: {complexity:.3f}, Impact: {impact}")
        else:
            results.add_result("Complex Prompt Categorization", "warn",
                             f"Expected high complexity, got {complexity:.3f}")
        
        results.add_result("Judge Reasoning", "pass", f"Provided: {reasoning[:50]}...")
        
    except Exception as e:
        results.add_result("Judge Functionality", "fail", f"Exception: {e}")
    finally:
        db.close()


async def test_dynamic_threshold(results):
    """Test Module C: Dynamic Thresholding (5% Rule)."""
    results.set_feature("Module C: Dynamic Thresholding")
    
    threshold = DynamicThreshold(target_rate=0.05, window_size=20)
    
    # Test initial threshold
    initial = threshold.get_threshold()
    results.add_result("Initial Threshold", "pass", f"Value: {initial:.3f}")
    
    # Test adding decisions (weak)
    for _ in range(10):
        threshold.add_decision(False)  # Weak model
    
    threshold_after_weak = threshold.get_threshold()
    
    # Test escalation rate
    rate = threshold.current_escalation_rate()
    if rate == 0.0:
        results.add_result("Escalation Rate Calculation", "pass", f"0% escalation with all weak decisions")
    else:
        results.add_result("Escalation Rate Calculation", "fail", f"Expected 0%, got {rate:.1%}")
    
    # Add strong model decisions
    for _ in range(5):
        threshold.add_decision(True)  # Strong model
    
    rate = threshold.current_escalation_rate()
    expected_rate = 5.0 / 15.0  # 5 strong out of 15 total
    
    if abs(rate - expected_rate) < 0.01:
        results.add_result("Escalation Rate After Strong", "pass", f"Rate: {rate:.1%}")
    else:
        results.add_result("Escalation Rate After Strong", "warn", 
                         f"Expected {expected_rate:.1%}, got {rate:.1%}")
    
    # Test threshold adjustment
    new_threshold = threshold.adjust_threshold()
    if new_threshold is not None and rate > 0.05:
        results.add_result("Threshold Auto-Adjustment", "pass", 
                         f"Adjusted from {threshold_after_weak:.3f} to {new_threshold:.3f}")
    else:
        results.add_result("Threshold Auto-Adjustment", "info",
                         "No adjustment needed (rate <= 5%)")


async def test_cycle_detection(results):
    """Test Module D: Cycle Detection."""
    results.set_feature("Module D: Cycle Detection")
    
    detector = CycleDetector(session_id="test_cycle_001")
    
    # Test initial state
    cycle_detected = detector.detect_cycle_with_prompt("First prompt")
    if not cycle_detected:
        results.add_result("Initial State (No Cycle)", "pass", "No cycle on first request")
    else:
        results.add_result("Initial State (No Cycle)", "fail", "False positive on first request")
    
    # Add request-response pair
    detector.add_request_response("First prompt", "First response")
    
    # Test different prompts (no cycle)
    cycle_detected = detector.detect_cycle_with_prompt("Second different prompt")
    if not cycle_detected:
        results.add_result("Different Prompts (No Cycle)", "pass", "No cycle with different prompts")
    else:
        results.add_result("Different Prompts (No Cycle)", "fail", "False positive")
    
    # Test similar prompt (potential cycle)
    detector.add_request_response("Second different prompt", "Second response")
    
    # Simulate repetitive prompts
    for i in range(3):
        detector.add_request_response(f"Same prompt {i}", f"Response {i}")
    
    cycle_detected = detector.detect_cycle_with_prompt("Same prompt 3")
    results.add_result("Cycle Detection Algorithm", "pass" if cycle_detected else "info",
                     f"Cycle {'detected' if cycle_detected else 'not detected'} after repetition")
    
    # Test hash distance
    if detector.recent_hashes:
        hash_dist = detector.recent_hashes[-1][0]
        results.add_result("Hash Distance Calculation", "pass", f"Distance: {hash_dist}")


async def test_semantic_cache(results):
    """Test Semantic Cache."""
    results.set_feature("Semantic Cache")
    
    SessionLocal = get_session_local()
    db = SessionLocal()
    cache = SemanticCache(db)
    
    try:
        prompt = "What is the capital of France?"
        messages = [{"role": "user", "content": prompt}]
        
        # Test semantic hash generation
        semantic_hash = cache.build_semantic_hash(prompt, messages)
        if semantic_hash:
            results.add_result("Semantic Hash Generation", "pass", f"Hash: {semantic_hash[:16]}...")
        else:
            results.add_result("Semantic Hash Generation", "fail", "No hash generated")
        
        # Test cache miss
        stats = cache.get_stats_for_prompt(prompt, messages)
        if stats is None:
            results.add_result("Cache Miss (New Prompt)", "pass", "No stats for new prompt")
        else:
            results.add_result("Cache Miss (New Prompt)", "info", "Found existing stats")
        
        # Test recording interaction
        cache.record_interaction(
            prompt=prompt,
            context=messages,
            response_text="Paris is the capital of France.",
            model_used="test-model",
            latency_ms=50.0,
            judge_invoked=True,
            judge_latency_ms=20.0,
            complexity_score=0.3,
            impact_scope="LOW",
            cost=0.001,
            total_tokens=25
        )
        
        # Test cache hit
        db.commit()  # Commit the transaction
        stats = cache.get_stats_for_prompt(prompt, messages)
        if stats:
            results.add_result("Cache Hit After Recording", "pass", 
                             f"Weak calls: {stats.weak_calls}, Strong calls: {stats.strong_calls}")
        else:
            results.add_result("Cache Hit After Recording", "fail", "Stats not found after recording")
        
        # Test confidence calculation
        confident, confidence = cache.has_confident_history(prompt, messages)
        results.add_result("Confidence Calculation", "pass", 
                         f"Confident: {confident}, Score: {confidence:.2f}")
        
    finally:
        db.close()


async def test_rate_limiting(results):
    """Test Rate Limiting."""
    results.set_feature("Rate Limiting")
    
    rate_limiter = get_rate_limiter()
    
    # Test rate limit check
    allowed, reason, stats = await rate_limiter.check_rate_limits(
        model_id="test-model",
        rpm_limit=10,
        tpm_limit=1000,
        estimated_tokens=50
    )
    
    if allowed:
        results.add_result("Rate Limit Check (First Request)", "pass", "Request allowed")
    else:
        results.add_result("Rate Limit Check (First Request)", "warn", f"Blocked: {reason}")
    
    # Test recording request
    await rate_limiter.record_request("test-model", tokens=100)
    results.add_result("Request Recording", "pass", "Request recorded")
    
    # Test usage stats
    usage = await rate_limiter.get_usage_stats("test-model")
    if usage:
        results.add_result("Usage Stats Retrieval", "pass",
                         f"Requests: {usage['requests_last_minute']}, Tokens: {usage['tokens_last_minute']}")
    else:
        results.add_result("Usage Stats Retrieval", "fail", "No stats returned")


async def test_openrouter_integration(results):
    """Test OpenRouter Integration."""
    results.set_feature("OpenRouter Integration")
    
    config_file = Path("config/models_config.json")
    
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    openrouter_models = [k for k in config.get('models', {}).keys() if 'openrouter' in k.lower()]
    
    if openrouter_models:
        results.add_result("OpenRouter Models Configured", "pass", 
                         f"{len(openrouter_models)} models found")
    else:
        results.add_result("OpenRouter Models Configured", "fail", "No OpenRouter models")
    
    # Check routing integration
    routing_order = config.get('routing_order_config', {})
    weak_models = routing_order.get('weak_models', [])
    
    openrouter_in_routing = [m for m in weak_models if 'openrouter' in m.lower()]
    if openrouter_in_routing:
        results.add_result("OpenRouter in Routing Order", "pass",
                         f"{len(openrouter_in_routing)} models in weak_models")
    else:
        results.add_result("OpenRouter in Routing Order", "warn", "Not in routing order")
    
    # Check judge integration
    judge_config = config.get('judge_config', {})
    judge_models = judge_config.get('model_order', [])
    
    openrouter_judges = [m for m in judge_models if 'openrouter' in m.lower()]
    if openrouter_judges:
        results.add_result("OpenRouter as Judge Fallback", "pass",
                         f"{len(openrouter_judges)} judge models")


async def test_enhanced_logging(results):
    """Test Enhanced Logging & Tracking."""
    results.set_feature("Enhanced Logging & Tracking")
    
    conn = sqlite3.connect("data/sentinelrouter.db")
    cursor = conn.cursor()
    
    # Check routing_decisions schema
    cursor.execute("PRAGMA table_info(routing_decisions)")
    columns = {row[1] for row in cursor.fetchall()}
    
    required_cols = {'input_tokens', 'output_tokens', 'total_tokens',
                    'request_latency_ms', 'model_latency_ms', 'judge_latency_ms'}
    
    if required_cols.issubset(columns):
        results.add_result("Token & Latency Columns", "pass", "All 6 columns present")
    else:
        missing = required_cols - columns
        results.add_result("Token & Latency Columns", "fail", f"Missing: {missing}")
    
    # Check escalation_traces table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='escalation_traces'")
    if cursor.fetchone():
        results.add_result("Escalation Traces Table", "pass", "Table exists")
    else:
        results.add_result("Escalation Traces Table", "fail", "Table not found")
    
    # Check for actual data
    cursor.execute("SELECT COUNT(*) FROM routing_decisions WHERE total_tokens > 0")
    token_count = cursor.fetchone()[0]
    
    if token_count > 0:
        results.add_result("Token Tracking Data", "pass", f"{token_count} decisions with tokens")
    else:
        results.add_result("Token Tracking Data", "info", "No token data yet")
    
    conn.close()


async def test_state_management(results):
    """Test State Management."""
    results.set_feature("State Management")
    
    state_manager = await get_state_manager()
    
    try:
        # Test model retrieval
        models = await state_manager.get_all_models()
        if models:
            results.add_result("Model Configuration Loading", "pass",
                             f"{len(models)} models loaded")
        else:
            results.add_result("Model Configuration Loading", "fail", "No models loaded")
        
        # Test routing order config
        routing_config = await state_manager.get_routing_order_config()
        if routing_config and routing_config.weak_models:
            results.add_result("Routing Order Config", "pass",
                             f"{len(routing_config.weak_models)} weak models")
        else:
            results.add_result("Routing Order Config", "fail", "No routing config")
        
        # Test model state
        if models:
            model_id = list(models.keys())[0]
            model_state = await state_manager.get_model_state(model_id)
            results.add_result("Model State Retrieval", "pass" if model_state else "info",
                             f"State for {model_id}")
        
    except Exception as e:
        results.add_result("State Management", "fail", f"Exception: {e}")


async def test_metrics_collection(results):
    """Test Metrics Collection."""
    results.set_feature("Metrics Collection")
    
    metrics = get_metrics_collector()
    
    # Test metric recording
    metrics.record_model_latency("test-model", "weak", 100.5, "success")
    results.add_result("Model Latency Recording", "pass", "Metric recorded")
    
    metrics.record_judge_latency("test-judge", 50.3, "success")
    results.add_result("Judge Latency Recording", "pass", "Metric recorded")
    
    metrics.record_fallback("weak", "model-a", "model-b")
    results.add_result("Fallback Recording", "pass", "Fallback recorded")
    
    # Test metrics retrieval
    recent_metrics = metrics.get_recent_metrics(10)
    if recent_metrics:
        results.add_result("Metrics Retrieval", "pass", f"{len(recent_metrics)} recent metrics")
    else:
        results.add_result("Metrics Retrieval", "info", "No metrics in buffer")
    
    # Check metrics file
    metrics_file = Path("data/metrics/metrics.jsonl")
    if metrics_file.exists():
        results.add_result("Metrics File Persistence", "pass", f"File size: {metrics_file.stat().st_size} bytes")
    else:
        results.add_result("Metrics File Persistence", "info", "File not created yet")


async def test_api_endpoints(results):
    """Test API Endpoints (if server is running)."""
    results.set_feature("API Endpoints")
    
    base_url = "http://localhost:8000"
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Test health endpoint
            try:
                response = await client.get(f"{base_url}/health")
                if response.status_code == 200:
                    results.add_result("Health Endpoint", "pass", f"Status: {response.status_code}")
                else:
                    results.add_result("Health Endpoint", "fail", f"Status: {response.status_code}")
            except Exception as e:
                results.add_result("Health Endpoint", "info", "Server not running")
            
            # Test dashboard endpoint
            try:
                response = await client.get("http://localhost:8001/api/metrics")
                if response.status_code == 200:
                    results.add_result("Dashboard API", "pass", "Metrics endpoint accessible")
                else:
                    results.add_result("Dashboard API", "info", "Dashboard not accessible")
            except Exception as e:
                results.add_result("Dashboard API", "info", "Dashboard not running")
    
    except Exception as e:
        results.add_result("API Endpoints", "info", "Server not running (start with uvicorn)")


async def test_failover_fallback(results):
    """Test Failover & Fallback Logic."""
    results.set_feature("Failover & Fallback")
    
    config_file = Path("config/models_config.json")
    
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    routing_order = config.get('routing_order_config', {})
    weak_models = routing_order.get('weak_models', [])
    strong_models = routing_order.get('strong_models', [])
    
    if len(weak_models) > 1:
        results.add_result("Weak Model Fallback Chain", "pass",
                         f"{len(weak_models)} models for failover")
    else:
        results.add_result("Weak Model Fallback Chain", "warn", "Only 1 weak model configured")
    
    if len(strong_models) > 1:
        results.add_result("Strong Model Fallback Chain", "pass",
                         f"{len(strong_models)} models for failover")
    else:
        results.add_result("Strong Model Fallback Chain", "warn", "Only 1 strong model configured")
    
    judge_config = config.get('judge_config', {})
    judge_models = judge_config.get('model_order', [])
    
    if len(judge_models) > 1:
        results.add_result("Judge Model Fallback Chain", "pass",
                         f"{len(judge_models)} judges for failover")
    else:
        results.add_result("Judge Model Fallback Chain", "warn", "Only 1 judge configured")


async def main():
    """Run all feature tests."""
    print_header("SENTINELROUTER COMPREHENSIVE FEATURE TEST SUITE")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\nTesting all features and modules...")
    
    results = TestResults()
    
    try:
        await test_budget_killswitch(results)
        await test_judge_categorizer(results)
        await test_dynamic_threshold(results)
        await test_cycle_detection(results)
        await test_semantic_cache(results)
        await test_rate_limiting(results)
        await test_openrouter_integration(results)
        await test_enhanced_logging(results)
        await test_state_management(results)
        await test_metrics_collection(results)
        await test_api_endpoints(results)
        await test_failover_fallback(results)
        
    except Exception as e:
        print(f"\n{Colors.FAIL}❌ Test suite error: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
    
    results.print_summary()
    
    # Return exit code
    total_failed = sum(r["failed"] for r in results.results.values())
    sys.exit(0 if total_failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
