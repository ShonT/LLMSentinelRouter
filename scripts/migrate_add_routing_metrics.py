"""
Database migration script to add routing metrics columns and escalation traces table.

This script adds six new columns to the routing_decisions table for token and latency tracking:
- input_tokens: INTEGER DEFAULT 0
- output_tokens: INTEGER DEFAULT 0
- total_tokens: INTEGER DEFAULT 0
- request_latency_ms: REAL DEFAULT 0.0
- model_latency_ms: REAL DEFAULT 0.0
- judge_latency_ms: REAL (nullable)

And creates a new escalation_traces table with detailed escalation tracing columns.

Usage:
    python scripts/migrate_add_routing_metrics.py
"""

import sys
import os
import logging
from pathlib import Path

# Add parent directory to path to import sentinelrouter
sys.path.insert(0, str(Path(__file__).parent.parent))

from sentinelrouter.sentinelrouter.database import engine, SessionLocal
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def add_routing_decision_columns(db):
    """Add token and latency tracking columns to routing_decisions table."""
    
    try:
        # Check which columns already exist
        result = db.execute(text("PRAGMA table_info(routing_decisions)"))
        existing_columns = {row[1] for row in result.fetchall()}
        
        columns_to_add = [
            ("input_tokens", "INTEGER DEFAULT 0"),
            ("output_tokens", "INTEGER DEFAULT 0"),
            ("total_tokens", "INTEGER DEFAULT 0"),
            ("request_latency_ms", "REAL DEFAULT 0.0"),
            ("model_latency_ms", "REAL DEFAULT 0.0"),
            ("judge_latency_ms", "REAL")
        ]
        
        added_count = 0
        for column_name, column_type in columns_to_add:
            if column_name in existing_columns:
                logger.info(f"✓ Column '{column_name}' already exists in routing_decisions table")
                continue
            
            logger.info(f"Adding column '{column_name}' to routing_decisions table...")
            db.execute(text(f"""
                ALTER TABLE routing_decisions 
                ADD COLUMN {column_name} {column_type}
            """))
            added_count += 1
        
        if added_count > 0:
            db.commit()
            logger.info(f"✓ Successfully added {added_count} columns to routing_decisions table")
        else:
            logger.info("✓ All columns already present in routing_decisions table")
        
        # Verify columns were added
        result = db.execute(text("PRAGMA table_info(routing_decisions)"))
        final_columns = {row[1] for row in result.fetchall()}
        
        missing = [col for col, _ in columns_to_add if col not in final_columns]
        if missing:
            logger.error(f"✗ Migration verification failed: missing columns {missing}")
            return False
        
        logger.info("✓ All routing decision columns verified successfully")
        return True
        
    except Exception as e:
        logger.error(f"✗ Failed to add routing decision columns: {e}")
        db.rollback()
        return False


def create_escalation_traces_table(db):
    """Create the escalation_traces table if it doesn't exist."""
    
    try:
        # Check if table already exists
        result = db.execute(text("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='escalation_traces'
        """))
        
        if result.fetchone():
            logger.info("✓ Table 'escalation_traces' already exists")
            return True
        
        logger.info("Creating 'escalation_traces' table...")
        
        # Create table with all columns as defined in models.py
        db.execute(text("""
            CREATE TABLE escalation_traces (
                trace_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id VARCHAR NOT NULL,
                request_id VARCHAR UNIQUE,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                
                -- Request info
                request_preview TEXT,
                
                -- Cycle detection trace
                cycle_detected BOOLEAN DEFAULT 0,
                cycle_hash_distance REAL,
                cycle_repetition_count INTEGER,
                
                -- Semantic cache trace
                cache_hit BOOLEAN DEFAULT 0,
                cache_confidence REAL,
                cache_recommendation VARCHAR,
                cache_weak_calls INTEGER DEFAULT 0,
                cache_strong_calls INTEGER DEFAULT 0,
                
                -- Judge trace
                judge_invoked BOOLEAN DEFAULT 0,
                judge_complexity_score REAL,
                judge_impact_scope VARCHAR,
                judge_reasoning TEXT,
                judge_latency_ms REAL,
                
                -- Routing decision trace
                initial_route_decision VARCHAR NOT NULL,
                final_route_decision VARCHAR NOT NULL,
                escalation_reason TEXT,
                
                -- Final model used
                model_used VARCHAR NOT NULL,
                
                -- Foreign key constraint
                FOREIGN KEY (session_id) REFERENCES sessions (session_id)
            )
        """))
        
        # Create indexes for performance
        db.execute(text("CREATE INDEX idx_escalation_traces_session_id ON escalation_traces(session_id)"))
        db.execute(text("CREATE INDEX idx_escalation_traces_request_id ON escalation_traces(request_id)"))
        db.execute(text("CREATE INDEX idx_escalation_traces_timestamp ON escalation_traces(timestamp)"))
        
        db.commit()
        logger.info("✓ Successfully created 'escalation_traces' table with indexes")
        
        # Verify table creation
        result = db.execute(text("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='escalation_traces'
        """))
        
        if not result.fetchone():
            logger.error("✗ Table verification failed: escalation_traces not found")
            return False
        
        logger.info("✓ Table 'escalation_traces' verified successfully")
        return True
        
    except Exception as e:
        logger.error(f"✗ Failed to create escalation_traces table: {e}")
        db.rollback()
        return False


def verify_migration(db):
    """Verify the migration was successful."""
    
    try:
        # Verify routing_decisions columns
        result = db.execute(text("PRAGMA table_info(routing_decisions)"))
        columns = {row[1]: row[2] for row in result.fetchall()}
        
        required_columns = {
            'input_tokens': 'INTEGER',
            'output_tokens': 'INTEGER', 
            'total_tokens': 'INTEGER',
            'request_latency_ms': 'REAL',
            'model_latency_ms': 'REAL',
            'judge_latency_ms': 'REAL'
        }
        
        logger.info("Verifying routing_decisions columns:")
        for col, expected_type in required_columns.items():
            if col not in columns:
                logger.error(f"✗ Missing column: {col}")
                return False
            logger.info(f"  ✓ {col}: {columns[col]}")
        
        # Verify escalation_traces table structure
        result = db.execute(text("PRAGMA table_info(escalation_traces)"))
        trace_columns = {row[1] for row in result.fetchall()}
        
        required_trace_columns = {
            'trace_id', 'session_id', 'request_id', 'timestamp',
            'request_preview', 'cycle_detected', 'cycle_hash_distance',
            'cycle_repetition_count', 'cache_hit', 'cache_confidence',
            'cache_recommendation', 'cache_weak_calls', 'cache_strong_calls',
            'judge_invoked', 'judge_complexity_score', 'judge_impact_scope',
            'judge_reasoning', 'judge_latency_ms', 'initial_route_decision',
            'final_route_decision', 'escalation_reason', 'model_used'
        }
        
        logger.info("Verifying escalation_traces columns:")
        for col in required_trace_columns:
            if col not in trace_columns:
                logger.error(f"✗ Missing column in escalation_traces: {col}")
                return False
        
        logger.info(f"  ✓ All {len(required_trace_columns)} columns present")
        
        # Verify indexes
        result = db.execute(text("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND tbl_name='escalation_traces'
        """))
        indexes = {row[0] for row in result.fetchall()}
        
        required_indexes = {
            'idx_escalation_traces_session_id',
            'idx_escalation_traces_request_id', 
            'idx_escalation_traces_timestamp'
        }
        
        for idx in required_indexes:
            if idx not in indexes:
                logger.warning(f"⚠ Missing index: {idx}")
                # Not a critical failure, just warning
        
        logger.info("✓ Migration verification completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"✗ Verification failed: {e}")
        return False


def main():
    """Run the migration."""
    
    logger.info("=" * 60)
    logger.info("Database Migration: Add Routing Metrics & Escalation Traces")
    logger.info("=" * 60)
    
    db = SessionLocal()
    
    try:
        # Step 1: Add columns to routing_decisions
        logger.info("\n1. Adding routing decision columns...")
        if not add_routing_decision_columns(db):
            logger.error("Migration failed at step 1")
            sys.exit(1)
        
        # Step 2: Create escalation_traces table
        logger.info("\n2. Creating escalation_traces table...")
        if not create_escalation_traces_table(db):
            logger.error("Migration failed at step 2")
            sys.exit(1)
        
        # Step 3: Verify migration
        logger.info("\n3. Verifying migration...")
        if not verify_migration(db):
            logger.error("Migration verification failed")
            sys.exit(1)
        
        logger.info("=" * 60)
        logger.info("✓ Migration completed successfully!")
        logger.info("=" * 60)
        logger.info("\nSummary of changes:")
        logger.info("1. Added 6 columns to routing_decisions table:")
        logger.info("   - input_tokens, output_tokens, total_tokens")
        logger.info("   - request_latency_ms, model_latency_ms, judge_latency_ms")
        logger.info("2. Created escalation_traces table with 22 columns")
        logger.info("3. Added 3 indexes for performance")
        logger.info("\nNext steps:")
        logger.info("1. Restart the Docker container if running")
        logger.info("2. Test that new routing metrics are being collected")
        logger.info("3. Verify escalation traces are created during strong model escalations")
        
    except Exception as e:
        logger.error(f"✗ Unexpected error during migration: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()