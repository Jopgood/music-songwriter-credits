#!/usr/bin/env python3
"""
Script to import a catalog CSV file into the database.
"""

import os
import sys
import csv
import logging
import argparse
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import package modules
from songwriter_id.database.setup import setup_database, create_session
from songwriter_id.database.models import Track

def import_catalog(catalog_path, db_url=None):
    """Import a catalog CSV file into the database.
    
    Args:
        catalog_path: Path to the CSV file
        db_url: Database URL (optional, uses env var if not provided)
        
    Returns:
        Number of tracks imported
    """
    # Set up database
    engine = setup_database(db_url)
    if not engine:
        logger.error("Failed to set up database.")
        return 0
    
    # Create session
    Session = create_session(engine)
    if not Session:
        logger.error("Failed to create database session.")
        return 0
    
    session = Session()
    
    try:
        logger.info(f"Importing catalog from {catalog_path}")
        with open(catalog_path, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            
            track_count = 0
            for row in reader:
                # Check if track already exists
                existing = session.query(Track).filter_by(
                    title=row.get('title', ''),
                    artist_name=row.get('artist', '')
                ).first()
                
                if existing:
                    logger.info(f"Track '{row.get('title')}' by {row.get('artist')} already exists, skipping.")
                    continue
                
                track = Track(
                    title=row.get('title', ''),
                    artist_name=row.get('artist', ''),
                    release_title=row.get('release', ''),
                    duration=float(row.get('duration', 0)) if row.get('duration') else None,
                    audio_path=row.get('audio_path', ''),
                    identification_status='pending',
                    confidence_score=0.0
                )
                session.add(track)
                track_count += 1
                
                # Commit in batches to avoid memory issues
                if track_count % 100 == 0:
                    session.commit()
                    logger.info(f"Imported {track_count} tracks...")
            
            session.commit()
            logger.info(f"Successfully imported {track_count} tracks")
            return track_count
    
    except Exception as e:
        session.rollback()
        logger.error(f"Error importing catalog: {e}")
        return 0
    finally:
        session.close()

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description='Import a catalog CSV file into the database')
    parser.add_argument('--catalog', required=True, help='Path to catalog CSV file')
    parser.add_argument('--db-url', help='Database URL (overrides environment variable)')
    args = parser.parse_args()
    
    # Load environment variables
    load_dotenv()
    
    # Import catalog
    count = import_catalog(args.catalog, args.db_url)
    
    return 0 if count > 0 else 1

if __name__ == "__main__":
    sys.exit(main())
