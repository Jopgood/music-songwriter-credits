"""Main entry point for the songwriter identification system."""

import os
import sys
import logging
import argparse
from dotenv import load_dotenv
import yaml

from songwriter_id.pipeline import SongwriterIdentificationPipeline

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point for the application."""
    parser = argparse.ArgumentParser(description='Songwriter Identification System')
    parser.add_argument('--config', default='config/pipeline.yaml', help='Path to configuration file')
    parser.add_argument('--catalog', help='Path to catalog CSV file to process')
    parser.add_argument('--audio-path', help='Base path for audio files')
    parser.add_argument('--db-url', help='Database connection URL (overrides environment variable)')
    args = parser.parse_args()
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Get database URL from arguments or environment
    db_url = args.db_url or os.environ.get('DATABASE_URL')
    if not db_url:
        logger.error("No database URL provided. Use --db-url or set DATABASE_URL environment variable.")
        return 1
    
    try:
        logger.info(f"Starting Songwriter Identification System using config: {args.config}")
        
        # Load config (just to check it exists)
        try:
            with open(args.config, 'r') as config_file:
                config = yaml.safe_load(config_file)
                logger.info(f"Loaded configuration with {len(config.keys())} sections")
        except Exception as e:
            logger.warning(f"Failed to load config file {args.config}: {e}")
            logger.warning("Continuing with default configuration")
        
        # Initialize pipeline
        pipeline = SongwriterIdentificationPipeline(
            config_file=args.config,
            db_connection=db_url
        )
        
        # If catalog provided, process it
        if args.catalog:
            result = pipeline.process_catalog(
                catalog_path=args.catalog,
                audio_base_path=args.audio_path
            )
            logger.info(f"Catalog processing complete: {result}")
        else:
            logger.info("No catalog provided. System initialized and ready for processing.")
            # In a real app, this might run a service, API, or wait for jobs
            
        return 0
    except Exception as e:
        logger.error(f"Error in main application: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
