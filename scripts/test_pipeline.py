#!/usr/bin/env python3
"""Test script for running the full songwriter identification pipeline on a sample catalog."""

import argparse
import logging
import os
import sys
from pathlib import Path

# Add the parent directory to the path so we can import the module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from songwriter_id.pipeline import SongwriterIdentificationPipeline
from songwriter_id.database.setup import setup_database
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


def setup_logging():
    """Set up logging for the test script."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('pipeline_test.log')
        ]
    )


def setup_test_db(db_url):
    """Set up a test database.
    
    Args:
        db_url: Database connection string
    """
    print(f"Setting up test database at {db_url}...")
    
    # For SQLite, create the database file if it doesn't exist
    if db_url.startswith('sqlite:'):
        db_path = db_url.replace('sqlite:///', '')
        if db_path != ':memory:' and not os.path.exists(db_path):
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            print(f"Created database file: {db_path}")
    
    # Initialize the database schema
    setup_database(db_url)
    print("Database schema initialized.")


def print_database_stats(db_url):
    """Print statistics about the database.
    
    Args:
        db_url: Database connection string
    """
    print("\nDatabase Statistics:")
    
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Count tracks
        track_count = session.execute(text("SELECT COUNT(*) FROM tracks")).scalar()
        print(f"Total tracks: {track_count}")
        
        # Count songwriter credits
        credit_count = session.execute(text("SELECT COUNT(*) FROM songwriter_credits")).scalar()
        print(f"Total songwriter credits: {credit_count}")
        
        # Count identification attempts
        attempt_count = session.execute(text("SELECT COUNT(*) FROM identification_attempts")).scalar()
        print(f"Total identification attempts: {attempt_count}")
        
        # Identification status breakdown
        status_counts = session.execute(text(
            "SELECT identification_status, COUNT(*) FROM tracks GROUP BY identification_status"
        )).fetchall()
        
        print("\nIdentification Status Breakdown:")
        for status, count in status_counts:
            print(f"  {status}: {count}")
        
        # Top identified songwriters
        if credit_count > 0:
            top_songwriters = session.execute(text(
                "SELECT songwriter_name, role, COUNT(*) as count FROM songwriter_credits "
                "GROUP BY songwriter_name, role ORDER BY count DESC LIMIT 10"
            )).fetchall()
            
            print("\nTop Identified Songwriters:")
            for name, role, count in top_songwriters:
                print(f"  {name} ({role}): {count} tracks")
        
    finally:
        session.close()


def main():
    """Main function for the test script."""
    parser = argparse.ArgumentParser(description='Test the songwriter identification pipeline')
    
    parser.add_argument('--catalog', default='data/sample_catalog.csv', 
                        help='Path to the test catalog file')
    parser.add_argument('--config', default='config/pipeline.yaml', 
                        help='Path to the configuration file')
    parser.add_argument('--db', default='sqlite:///data/test_songwriter.db', 
                        help='Database connection string')
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging()
    
    # Set up test database
    setup_test_db(args.db)
    
    # Initialize the pipeline
    print(f"Initializing pipeline with config: {args.config}")
    pipeline = SongwriterIdentificationPipeline(
        config_file=args.config,
        db_connection=args.db
    )
    
    # Process the catalog
    print(f"Processing catalog: {args.catalog}")
    stats = pipeline.process_catalog(
        catalog_path=args.catalog
    )
    
    # Print results
    print("\nProcessing Results:")
    print(f"Status: {stats['status']}")
    
    if 'import' in stats:
        print("\nImport Statistics:")
        print(f"Tracks parsed: {stats['import']['tracks_parsed']}")
        print(f"Tracks added: {stats['import']['tracks_added']}")
        print(f"Tracks skipped: {stats['import']['tracks_skipped']}")
        print(f"Import errors: {stats['import']['import_errors']}")
    
    if 'identification' in stats:
        print("\nIdentification Statistics:")
        print(f"Tier 1 identified: {stats['identification'].get('tier1_identified', 0)}")
        print(f"Tier 2 identified: {stats['identification'].get('tier2_identified', 0)}")
        print(f"Tier 3 identified: {stats['identification'].get('tier3_identified', 0)}")
        print(f"Manual review: {stats['identification'].get('manual_review', 0)}")
        print(f"Total processed: {stats['identification'].get('total_processed', 0)}")
    
    # Print database statistics
    print_database_stats(args.db)


if __name__ == '__main__':
    main()
