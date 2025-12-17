#!/usr/bin/env python3
"""
Database migration script to add enhanced tracking:
1. Token columns to routing_decisions table
2. Latency columns to routing_decisions table
3. New escalation_traces table for strong model escalation tracking
"""

import sqlite3
from pathlib import Path
import sys

def migrate_database(db_path: str = "data/sentinelrouter.db"):
    """Add new columns and table for enhanced tracking."""
    db_path = Path(db_path)
    if not db_path.exists():
        print(f"❌ Database not found at {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("=" * 70)
    print("ENHANCED ROUTING DECISION TRACKING MIGRATION")
    print("=" * 70)
    print()
    
    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(routing_decisions)")
        columns = [row[1] for row in cursor.fetchall()]
        
        # Add new columns to routing_decisions if they don't exist
        new_columns = [
            ("input_tokens", "INTEGER DEFAULT 0"),
            ("output_tokens", "INTEGER DEFAULT 0"),
            ("total_tokens", "INTEGER DEFAULT 0"),
            ("request_latency_ms", "REAL DEFAULT 0.0"),
            ("model_latency_ms", "REAL DEFAULT 0.0"),
            ("judge_latency_ms", "REAL"),
        ]
        
        print("Phase 1: Adding token and latency columns to routing_decisions")
        print("-" * 70)
        for col_name, col_type in new_columns:
            if col_name not in columns:
                try:
                    cursor.execute(f"ALTER TABLE routing_decisions ADD COLUMN {col_name} {col_type}")
                    print(f"  ✅ Added column: routing_decisions.{col_name}")
                except sqlite3.OperationalError as e:
                    print(f"  ⚠️  Column {col_name} might already exist: {e}")
            else:
                print(f"  ℹ️  Column {col_name} already exists")
        
        print()
        print("Phase 2: Creating escalation_traces table")
        print("-" * 70)
        
        # Create escalation_traces table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS escalation_traces (
                trace_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                request_id TEXT UNIQUE,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                -- Request info
                request_preview TEXT,
                
                -- Cycle detection
                cycle_detected INTEGER DEFAULT 0,
                cycle_hash_distance REAL,
                cycle_repetition_count INTEGER,
                
                -- Semantic cache
                cache_hit INTEGER DEFAULT 0,
                cache_confidence REAL,
                cache_recommendation TEXT,
                cache_weak_calls INTEGER DEFAULT 0,
                cache_strong_calls INTEGER DEFAULT 0,
                
                -- Judge
                judge_invoked INTEGER DEFAULT 0,
                judge_complexity_score REAL,
                judge_impact_scope TEXT,
                judge_reasoning TEXT,
                judge_latency_ms REAL,
                
                -- Routing decision
                initial_route_decision TEXT,
                final_route_decision TEXT,
                escalation_reason TEXT,
                
                -- Model used
                model_used TEXT,
                
                FOREIGN KEY (session_id) REFERENCES sessions (session_id)
            )
        """)
        print("  ✅ Created escalation_traces table")
        
        # Create indexes for fast lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_escalation_traces_request_id 
            ON escalation_traces(request_id)
        """)
        print("  ✅ Created index on escalation_traces.request_id")
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_escalation_traces_session_id 
            ON escalation_traces(session_id)
        """)
        print("  ✅ Created index on escalation_traces.session_id")
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_escalation_traces_timestamp 
            ON escalation_traces(timestamp)
        """)
        print("  ✅ Created index on escalation_traces.timestamp")
        
        conn.commit()
        
        print()
        print("=" * 70)
        print("✅ Migration completed successfully!")
        print("=" * 70)
        print()
        
        # Verify the migration
        print("Verification:")
        print("-" * 70)
        cursor.execute("PRAGMA table_info(routing_decisions)")
        routing_cols = [row[1] for row in cursor.fetchall()]
        
        expected_cols = ['input_tokens', 'output_tokens', 'total_tokens', 
                        'request_latency_ms', 'model_latency_ms', 'judge_latency_ms']
        
        missing_cols = [col for col in expected_cols if col not in routing_cols]
        if missing_cols:
            print(f"  ⚠️  Missing columns in routing_decisions: {missing_cols}")
        else:
            print(f"  ✅ All expected columns exist in routing_decisions")
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='escalation_traces'")
        if cursor.fetchone():
            print(f"  ✅ escalation_traces table exists")
        else:
            print(f"  ⚠️  escalation_traces table not found")
        
        print()
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    success = migrate_database()
    sys.exit(0 if success else 1)
