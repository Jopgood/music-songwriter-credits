#!/usr/bin/env python3
"""
Database setup script for the songwriter identification system.
Creates the necessary tables and indexes in the database.
"""

import os
import argparse
import logging
from dotenv import load_dotenv
from sqlalchemy import create_engine
from songwriter_id.database.models import Base

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def setup_database(db_url: str, drop_existing: bool = False):
    """
    Set up the database schema.
    
    Args:
        db_url: Database connection URL
        drop_existing: Whether to drop existing tables
    """
    logger.info(f"Connecting to database: {db_url}")
    engine = create_engine(db_url)
    
    if drop_existing:
        logger.warning("Dropping existing tables...")
        Base.metadata.drop_all(engine)
    
    logger.info("Creating tables...")
    Base.metadata.create_all(engine)
    logger.info("Database setup complete!")

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description='Set up the songwriter identification database')
    parser.add_argument('--drop', action='store_true', help='Drop existing tables before creating new ones')
    parser.add_argument('--db-url', help='Database URL (overrides environment variable)')
    args = parser.parse_args()
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Get database URL from arguments or environment
    db_url = args.db_url or os.environ.get('DATABASE_URL')
    if not db_url:
        logger.error("No database URL provided. Use --db-url or set DATABASE_URL environment variable.")
        return 1
    
    try:
        setup_database(db_url, args.drop)
        return 0
    except Exception as e:
        logger.error(f"Error setting up database: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
