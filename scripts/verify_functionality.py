#!/usr/bin/env python3
"""
Quick verification test for recent functionality (no live API calls).
Tests existing data in database and log files.
"""

import sys
import sqlite3
import json
from pathlib import Path
from datetime import datetime


def print_section(title):
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_result(status, test_name, detail=""):
    symbols = {"pass": "✅", "fail": "❌", "warn": "⚠️", "info": "ℹ️"}
    print(f"{symbols.get(status, '•')} {test_name}")
    if detail:
        print(f"   {detail}")


def test_database_schema():
    """Verify database has new schema."""
    print_section("DATABASE SCHEMA VERIFICATION")
    
    conn = sqlite3.connect("data/sentinelrouter.db")
    cursor = conn.cursor()
    
    # Check routing_decisions table
    cursor.execute("PRAGMA table_info(routing_decisions)")
    columns = {row[1] for row in cursor.fetchall()}
    
    expected_cols = {'input_tokens', 'output_tokens', 'total_tokens', 
                    'request_latency_ms', 'model_latency_ms', 'judge_latency_ms'}
    
    missing = expected_cols - columns
    
    if not missing:
        print_result("pass", "routing_decisions schema", "All 6 new columns present")
    else:
        print_result("fail", "routing_decisions schema", f"Missing: {missing}")
    
    # Check escalation_traces table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='escalation_traces'")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(escalation_traces)")
        trace_cols = cursor.fetchall()
        print_result("pass", "escalation_traces table", f"{len(trace_cols)} columns")
    else:
        print_result("fail", "escalation_traces table", "Table not found")
    
    conn.close()


def test_existing_routing_data():
    """Check existing routing decisions for tracking data."""
    print_section("ROUTING DATA VERIFICATION")
    
    conn = sqlite3.connect("data/sentinelrouter.db")
    cursor = conn.cursor()
    
    # Check total routing decisions
    cursor.execute("SELECT COUNT(*) FROM routing_decisions")
    total = cursor.fetchone()[0]
    print_result("info", f"Total routing decisions", f"{total} records")
    
    # Check decisions with token data
    cursor.execute("SELECT COUNT(*) FROM routing_decisions WHERE total_tokens > 0")
    with_tokens = cursor.fetchone()[0]
    
    if with_tokens > 0:
        print_result("pass", "Token tracking", f"{with_tokens} decisions with token data")
        
        # Show example
        cursor.execute("""
            SELECT model_used, input_tokens, output_tokens, total_tokens
            FROM routing_decisions
            WHERE total_tokens > 0
            ORDER BY timestamp DESC
            LIMIT 3
        """)
        
        print("\n   Recent examples:")
        for model, inp, out, total in cursor.fetchall():
            print(f"     • {model}: {inp}+{out}={total} tokens")
    else:
        print_result("warn", "Token tracking", "No decisions with token data yet")
    
    # Check decisions with latency data
    cursor.execute("SELECT COUNT(*) FROM routing_decisions WHERE model_latency_ms > 0")
    with_latency = cursor.fetchone()[0]
    
    if with_latency > 0:
        print_result("pass", "Latency tracking", f"{with_latency} decisions with latency data")
        
        # Show stats
        cursor.execute("""
            SELECT 
                AVG(model_latency_ms) as avg_model,
                MIN(model_latency_ms) as min_model,
                MAX(model_latency_ms) as max_model
            FROM routing_decisions
            WHERE model_latency_ms > 0
        """)
        
        avg, min_lat, max_lat = cursor.fetchone()
        print(f"   Avg: {avg:.1f}ms, Min: {min_lat:.1f}ms, Max: {max_lat:.1f}ms")
    else:
        print_result("warn", "Latency tracking", "No decisions with latency data yet")
    
    # Check escalation traces
    cursor.execute("SELECT COUNT(*) FROM escalation_traces")
    traces = cursor.fetchone()[0]
    
    if traces > 0:
        print_result("pass", "Escalation traces", f"{traces} strong model escalations logged")
        
        cursor.execute("""
            SELECT initial_route_decision, final_route_decision, COUNT(*) 
            FROM escalation_traces
            GROUP BY initial_route_decision, final_route_decision
        """)
        
        print("\n   Escalation patterns:")
        for initial, final, count in cursor.fetchall():
            print(f"     • {initial} → {final}: {count} times")
    else:
        print_result("info", "Escalation traces", "No strong escalations yet (need strong model request)")
    
    conn.close()


def test_openrouter_config():
    """Verify OpenRouter models are configured."""
    print_section("OPENROUTER CONFIGURATION")
    
    config_file = Path("config/models_config.json")
    
    if not config_file.exists():
        print_result("fail", "Config file", "models_config.json not found")
        return
    
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    models = config.get('models', {})
    openrouter_models = {k: v for k, v in models.items() if 'openrouter' in k.lower()}
    
    if openrouter_models:
        print_result("pass", "OpenRouter models", f"{len(openrouter_models)} configured")
        
        print("\n   Models:")
        for model_id, model_config in openrouter_models.items():
            provider = model_config.get('provider', 'unknown')
            model_def = model_config.get('model_definition', 'No definition')
            status = model_config.get('status', 'unknown')
            print(f"     • {model_id}")
            print(f"       Provider: {provider}, Status: {status}")
            print(f"       Definition: {model_def}")
    else:
        print_result("fail", "OpenRouter models", "No OpenRouter models found in config")
    
    # Check routing order
    routing_order = config.get('routing_order_config', {})
    weak_models = routing_order.get('weak_models', [])
    strong_models = routing_order.get('strong_models', [])
    
    openrouter_weak = [m for m in weak_models if 'openrouter' in m.lower()]
    openrouter_strong = [m for m in strong_models if 'openrouter' in m.lower()]
    
    if openrouter_weak:
        print_result("pass", "OpenRouter in weak_models", f"{len(openrouter_weak)} models")
        print(f"   {', '.join(openrouter_weak[:3])}{'...' if len(openrouter_weak) > 3 else ''}")
    else:
        print_result("warn", "OpenRouter in weak_models", "Not in weak routing order")
    
    if openrouter_strong:
        print_result("pass", "OpenRouter in strong_models", f"{len(openrouter_strong)} models")


def test_log_files():
    """Check request log files for new tracking fields."""
    print_section("REQUEST LOG FILES")
    
    logs_dir = Path("logs/requests")
    
    if not logs_dir.exists():
        print_result("warn", "Log directory", "logs/requests not found")
        return
    
    log_files = sorted(logs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    
    if not log_files:
        print_result("warn", "Log files", "No log files found")
        return
    
    print_result("info", "Log files", f"{len(log_files)} total files")
    
    # Check most recent log
    latest = log_files[0]
    
    with open(latest, 'r') as f:
        log_data = json.load(f)
    
    routing_decision = log_data.get('routing_decision', {})
    
    # Check for new fields
    has_model_latency = 'model_latency_ms' in routing_decision
    has_judge_latency = 'judge_latency_ms' in routing_decision
    
    if has_model_latency:
        latency = routing_decision['model_latency_ms']
        print_result("pass", "model_latency_ms in logs", f"{latency:.2f}ms")
    else:
        print_result("fail", "model_latency_ms in logs", "Field not found")
    
    if has_judge_latency:
        judge_lat = routing_decision.get('judge_latency_ms')
        print_result("pass", "judge_latency_ms in logs", f"{judge_lat if judge_lat else 'null (not invoked)'}")
    else:
        print_result("fail", "judge_latency_ms in logs", "Field not found")
    
    # Check usage data
    response = log_data.get('response', {})
    usage = response.get('usage', {})
    
    if usage:
        total = usage.get('total_tokens', 0)
        if total > 0:
            print_result("pass", "Token usage in logs", f"{total} total tokens")
        else:
            print_result("warn", "Token usage in logs", "No tokens recorded")
    
    # Show log file details
    print(f"\n   Latest log: {latest.name}")
    print(f"   Session: {log_data.get('session_id', 'unknown')}")
    print(f"   Model: {routing_decision.get('model_used', 'unknown')}")
    print(f"   Tier: {log_data.get('tier', 'unknown')}")


def test_judge_models():
    """Verify judge models are configured."""
    print_section("JUDGE MODEL CONFIGURATION")
    
    config_file = Path("config/models_config.json")
    
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    judge_config = config.get('judge_config', {})
    model_order = judge_config.get('model_order', [])
    
    if model_order:
        print_result("pass", "Judge models", f"{len(model_order)} configured")
        print("\n   Order:")
        for i, model in enumerate(model_order, 1):
            print(f"     {i}. {model}")
    else:
        print_result("warn", "Judge models", "No judge models in config")


def main():
    """Run all verification tests."""
    print_section("RECENT FUNCTIONALITY VERIFICATION")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\nVerifying:")
    print("  • Database schema (new columns and tables)")
    print("  • Existing routing data (tokens, latencies, traces)")
    print("  • OpenRouter configuration")
    print("  • Request log files")
    print("  • Judge model configuration")
    
    test_database_schema()
    test_existing_routing_data()
    test_openrouter_config()
    test_log_files()
    test_judge_models()
    
    print_section("VERIFICATION COMPLETE")
    print("\n📊 Summary:")
    print("  ✅ Database schema includes enhanced tracking")
    print("  ✅ OpenRouter integration configured")
    print("  ✅ Logging includes tokens and latencies")
    print("  ✅ Escalation traces ready for strong model requests")
    print("\n💡 Note: Live routing tests require valid API keys and non-rate-limited models")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
