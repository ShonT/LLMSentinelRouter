#!/usr/bin/env python3
"""
Database migration script to add cost_source and computed_cost columns
to routing_decisions table.

Usage:
    python scripts/migrate_cost_tracking.py
"""

import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sentinelrouter.sentinelrouter.database import get_db, get_engine


def migrate_cost_tracking():
    """Add cost_source and computed_cost columns to routing_decisions table."""
    
    engine = get_engine()
    
    print("Starting cost tracking migration...")
    
    # Check if columns already exist
    with engine.connect() as conn:
        # Check for cost_source column
        try:
            result = conn.execute(text(
                "SELECT cost_source FROM routing_decisions LIMIT 1"
            ))
            result.close()
            print("✓ cost_source column already exists")
            cost_source_exists = True
        except Exception:
            cost_source_exists = False
        
        # Check for computed_cost column
        try:
            result = conn.execute(text(
                "SELECT computed_cost FROM routing_decisions LIMIT 1"
            ))
            result.close()
            print("✓ computed_cost column already exists")
            computed_cost_exists = True
        except Exception:
            computed_cost_exists = False
        
        # Add missing columns
        if not cost_source_exists:
            print("Adding cost_source column...")
            conn.execute(text(
                "ALTER TABLE routing_decisions ADD COLUMN cost_source VARCHAR DEFAULT 'unknown'"
            ))
            conn.commit()
            print("✓ Added cost_source column")
        
        if not computed_cost_exists:
            print("Adding computed_cost column...")
            conn.execute(text(
                "ALTER TABLE routing_decisions ADD COLUMN computed_cost FLOAT"
            ))
            conn.commit()
            print("✓ Added computed_cost column")
        
        if cost_source_exists and computed_cost_exists:
            print("✓ All columns already exist - nothing to migrate")
        else:
            print("\n✓ Migration completed successfully!")
            print("\nNew columns added:")
            print("  - cost_source: tracks whether cost is from 'provider', 'computed', or 'unknown'")
            print("  - computed_cost: stores fallback computed cost for audit/debugging")


if __name__ == "__main__":
    try:
        migrate_cost_tracking()
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        sys.exit(1)
