"""
Database migration script to add tier column to sessions table.

This script adds a 'tier' column to the sessions table to support
tier-based rate limiting (free, paid, premium).

Usage:
    python scripts/migrate_add_session_tier.py
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


def migrate_add_tier_column():
    """Add tier column to sessions table if it doesn't exist."""
    
    db = SessionLocal()
    try:
        # Check if tier column already exists
        result = db.execute(text("PRAGMA table_info(sessions)"))
        columns = [row[1] for row in result.fetchall()]
        
        if 'tier' in columns:
            logger.info("✓ 'tier' column already exists in sessions table")
            return True
        
        logger.info("Adding 'tier' column to sessions table...")
        
        # Add tier column with default value 'free'
        db.execute(text("""
            ALTER TABLE sessions 
            ADD COLUMN tier VARCHAR DEFAULT 'free' NOT NULL
        """))
        db.commit()
        
        logger.info("✓ Successfully added 'tier' column")
        
        # Verify the column was added
        result = db.execute(text("PRAGMA table_info(sessions)"))
        columns = [row[1] for row in result.fetchall()]
        
        if 'tier' in columns:
            logger.info("✓ Migration verified successfully")
            return True
        else:
            logger.error("✗ Migration failed - tier column not found after addition")
            return False
            
    except Exception as e:
        logger.error(f"✗ Migration failed: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def update_existing_sessions():
    """Update existing sessions to have 'free' tier if NULL."""
    
    db = SessionLocal()
    try:
        logger.info("Updating existing sessions to 'free' tier...")
        
        result = db.execute(text("""
            UPDATE sessions 
            SET tier = 'free' 
            WHERE tier IS NULL
        """))
        db.commit()
        
        rows_updated = result.rowcount
        logger.info(f"✓ Updated {rows_updated} existing sessions to 'free' tier")
        return True
        
    except Exception as e:
        logger.error(f"✗ Failed to update existing sessions: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def verify_migration():
    """Verify the migration was successful."""
    
    db = SessionLocal()
    try:
        # Check column exists
        result = db.execute(text("PRAGMA table_info(sessions)"))
        columns = {row[1]: row[2] for row in result.fetchall()}
        
        if 'tier' not in columns:
            logger.error("✗ Verification failed: tier column not found")
            return False
        
        logger.info(f"✓ Column 'tier' exists with type: {columns['tier']}")
        
        # Check all sessions have a tier value
        result = db.execute(text("SELECT COUNT(*) FROM sessions WHERE tier IS NULL"))
        null_count = result.scalar()
        
        if null_count > 0:
            logger.warning(f"⚠ Found {null_count} sessions with NULL tier")
            return False
        
        logger.info("✓ All sessions have valid tier values")
        
        # Show tier distribution
        result = db.execute(text("""
            SELECT tier, COUNT(*) as count 
            FROM sessions 
            GROUP BY tier
        """))
        
        logger.info("Tier distribution:")
        for row in result.fetchall():
            logger.info(f"  {row[0]}: {row[1]} sessions")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Verification failed: {e}")
        return False
    finally:
        db.close()


def main():
    """Run the migration."""
    
    logger.info("=" * 60)
    logger.info("Database Migration: Add Session Tier Column")
    logger.info("=" * 60)
    
    # Step 1: Add tier column
    if not migrate_add_tier_column():
        logger.error("Migration failed at step 1")
        sys.exit(1)
    
    # Step 2: Update existing sessions
    if not update_existing_sessions():
        logger.error("Migration failed at step 2")
        sys.exit(1)
    
    # Step 3: Verify migration
    if not verify_migration():
        logger.error("Migration verification failed")
        sys.exit(1)
    
    logger.info("=" * 60)
    logger.info("✓ Migration completed successfully!")
    logger.info("=" * 60)
    logger.info("\nNext steps:")
    logger.info("1. Restart the Docker container")
    logger.info("2. Test tier-based rate limiting")
    logger.info("3. Update API clients to pass 'tier' parameter")


if __name__ == "__main__":
    main()
