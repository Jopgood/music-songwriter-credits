"""Main entry point for the songwriter identification system."""

import os
import sys
import logging
import argparse
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Try to import yaml, but provide a fallback
try:
    import yaml
    HAS_YAML = True
except ImportError:
    logger.warning("PyYAML not installed, will use default configuration")
    HAS_YAML = False

# Import after configure logging
from songwriter_id.database.setup import setup_database, create_session
from songwriter_id.pipeline import SongwriterIdentificationPipeline

def load_config(config_path):
    """Load configuration from YAML file.
    
    Args:
        config_path: Path to config file
        
    Returns:
        Configuration dictionary
    """
    if not HAS_YAML:
        logger.warning("PyYAML not installed, using default configuration")
        return {}
        
    try:
        with open(config_path, 'r') as config_file:
            config = yaml.safe_load(config_file)
            logger.info(f"Loaded configuration with {len(config.keys()) if config else 0} sections")
            return config
    except Exception as e:
        logger.warning(f"Failed to load config file {config_path}: {e}")
        return {}

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
        logger.info(f"Starting Songwriter Identification System")
        
        # Set up database
        engine = setup_database(db_url)
        if not engine:
            logger.error("Failed to set up database.")
            return 1
            
        # Load configuration
        config = load_config(args.config)
        
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
