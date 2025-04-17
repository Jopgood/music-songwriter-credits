"""Migration script to add track_isrc field to the tracks table."""

import argparse
import logging
import os
import sys
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, String, MetaData, Table, Index

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def migrate_database(db_url: str) -> None:
    """Add track_isrc column to tracks table.
    
    Args:
        db_url: Database connection URL
    """
    logger.info(f"Connecting to database")
    engine = create_engine(db_url)
    metadata = MetaData()
    
    # Reflect existing tracks table
    logger.info("Reflecting existing tracks table")
    tracks = Table('tracks', metadata, autoload_with=engine)
    
    # Check if column already exists
    if 'track_isrc' in tracks.columns:
        logger.info("track_isrc column already exists in tracks table")
        return
    
    # Create migration
    with engine.begin() as connection:
        logger.info("Adding track_isrc column to tracks table")
        connection.execute(
            f"ALTER TABLE tracks ADD COLUMN track_isrc VARCHAR(32)"
        )
        
        logger.info("Creating index on track_isrc column")
        connection.execute(
            f"CREATE INDEX ix_tracks_track_isrc ON tracks (track_isrc)"
        )
    
    logger.info("Migration completed successfully")

def main() -> None:
    """Main entry point for the migration script."""
    parser = argparse.ArgumentParser(description='Add track_isrc field to tracks table')
    parser.add_argument('--db-url', help='Database connection URL (overrides environment variable)')
    args = parser.parse_args()
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Get database URL from arguments or environment
    db_url = args.db_url or os.environ.get('DATABASE_URL')
    if not db_url:
        logger.error("No database URL provided. Use --db-url or set DATABASE_URL environment variable.")
        sys.exit(1)
    
    try:
        migrate_database(db_url)
    except Exception as e:
        logger.error(f"Error during migration: {e}", exc_info=True)
        sys.exit(1)
    
    sys.exit(0)

if __name__ == "__main__":
    main()
