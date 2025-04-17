#!/usr/bin/env python
"""
Migration script to add ISRC field to existing tracks table.

This script adds an ISRC column to the tracks table in the database
and ensures proper indexing. Run this script to upgrade an existing database.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Add parent directory to path so modules can be imported
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import Column, String, create_engine, text
from sqlalchemy.engine import Engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("migrate_add_isrc")

def add_isrc_column(engine: Engine) -> None:
    """
    Add the ISRC column to the tracks table.
    
    Args:
        engine: SQLAlchemy database engine
    """
    # Check if column already exists
    with engine.connect() as conn:
        # Check if ISRC column already exists
        result = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'tracks' AND column_name = 'isrc'"
        ))
        column_exists = result.fetchone() is not None
        
        if column_exists:
            logger.info("ISRC column already exists in tracks table")
            return
        
        # Add the ISRC column
        logger.info("Adding ISRC column to tracks table")
        conn.execute(text("ALTER TABLE tracks ADD COLUMN isrc VARCHAR(12)"))
        
        # Create an index on the ISRC column
        logger.info("Creating index on ISRC column")
        conn.execute(text("CREATE INDEX idx_tracks_isrc ON tracks (isrc)"))
        
        # Commit the transaction
        conn.commit()
        
    logger.info("Migration complete: ISRC column added to tracks table")

def main():
    parser = argparse.ArgumentParser(description="Add ISRC column to tracks table")
    parser.add_argument(
        "--db", 
        dest="db_connection", 
        help="Database connection string",
        default=os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/songwriter_db")
    )
    
    args = parser.parse_args()
    
    try:
        engine = create_engine(args.db_connection)
        add_isrc_column(engine)
        print("✅ Migration completed successfully")
        return 0
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        print(f"❌ Migration failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
