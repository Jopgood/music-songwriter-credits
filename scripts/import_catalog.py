#!/usr/bin/env python3
"""Script to import a music catalog and process it using the identification pipeline."""

import argparse
import logging
import os
import sys
from pathlib import Path

# Add the parent directory to the path so we can import the module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from songwriter_id.pipeline import SongwriterIdentificationPipeline


def setup_logging(log_level_name):
    """Set up logging with the specified level.
    
    Args:
        log_level_name: Name of the log level (DEBUG, INFO, WARNING, ERROR)
    """
    log_level = getattr(logging, log_level_name)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('catalog_import.log')
        ]
    )


def main():
    """Main function for the script."""
    parser = argparse.ArgumentParser(description='Import and process a music catalog')
    
    parser.add_argument('catalog_path', help='Path to the catalog file (CSV or Excel)')
    parser.add_argument('--config', default='config/pipeline.yaml', 
                        help='Path to the configuration file')
    parser.add_argument('--db', default='postgresql://localhost/songwriter_db', 
                        help='Database connection string')
    parser.add_argument('--audio-path', help='Base path for audio files')
    parser.add_argument('--log-level', default='INFO', 
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='Logging level')
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)
    
    # Validate inputs
    catalog_path = Path(args.catalog_path)
    if not catalog_path.exists():
        logger.error(f"Catalog file not found: {args.catalog_path}")
        sys.exit(1)
    
    config_path = Path(args.config)
    if not config_path.exists():
        logger.warning(f"Configuration file not found: {args.config}. Using default settings.")
    
    # Initialize the pipeline
    try:
        logger.info("Initializing songwriter identification pipeline")
        pipeline = SongwriterIdentificationPipeline(
            config_file=str(config_path),
            db_connection=args.db
        )
    except Exception as e:
        logger.error(f"Failed to initialize pipeline: {e}")
        sys.exit(1)
    
    # Process the catalog
    try:
        logger.info(f"Processing catalog: {args.catalog_path}")
        stats = pipeline.process_catalog(
            catalog_path=str(catalog_path),
            audio_base_path=args.audio_path
        )
        
        logger.info("Catalog processing complete")
        print("\nProcessing Results:")
        print(f"Tracks parsed: {stats['import']['tracks_parsed']}")
        print(f"Tracks added to database: {stats['import']['tracks_added']}")
        print(f"Tracks skipped: {stats['import']['tracks_skipped']}")
        print(f"Import errors: {stats['import']['import_errors']}")
        
        if 'identification' in stats and isinstance(stats['identification'], dict):
            print("\nIdentification Results:")
            print(f"Tracks identified via Tier 1 (metadata): {stats['identification'].get('tier1_identified', 0)}")
            print(f"Tracks identified via Tier 2 (enhanced): {stats['identification'].get('tier2_identified', 0)}")
            print(f"Tracks identified via Tier 3 (audio): {stats['identification'].get('tier3_identified', 0)}")
            print(f"Tracks requiring manual review: {stats['identification'].get('manual_review', 0)}")
            print(f"Total tracks processed: {stats['identification'].get('total_processed', 0)}")
        
    except Exception as e:
        logger.error(f"Error processing catalog: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
