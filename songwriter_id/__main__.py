"""Main entry point for the songwriter identification system."""

import os
import sys
import time
import logging
import argparse
import signal
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
from songwriter_id.scheduler import JobScheduler

# Global variable to store the scheduler so it can be stopped on SIGTERM
scheduler = None

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

def signal_handler(sig, frame):
    """Handle signals like SIGTERM and SIGINT by gracefully shutting down."""
    global scheduler
    
    logger.info(f"Received signal {sig}, shutting down...")
    
    if scheduler:
        logger.info("Stopping job scheduler...")
        scheduler.stop()
        
    logger.info("Shutdown complete.")
    sys.exit(0)

def main():
    """Main entry point for the application."""
    global scheduler
    
    parser = argparse.ArgumentParser(description='Songwriter Identification System')
    parser.add_argument('--config', default='config/pipeline.yaml', help='Path to configuration file')
    parser.add_argument('--catalog', help='Path to catalog CSV file to process')
    parser.add_argument('--audio-path', help='Base path for audio files')
    parser.add_argument('--db-url', help='Database connection URL (overrides environment variable)')
    parser.add_argument('--daemon', action='store_true', help='Run as a daemon with job scheduler')
    parser.add_argument('--jobs-dir', default='data/jobs', help='Directory for job files')
    args = parser.parse_args()
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
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
        
        # If catalog provided, process it directly
        if args.catalog:
            result = pipeline.process_catalog(
                catalog_path=args.catalog,
                audio_base_path=args.audio_path
            )
            logger.info(f"Catalog processing complete: {result}")
            return 0
            
        # If daemon mode is requested, start the job scheduler
        if args.daemon:
            logger.info("Starting job scheduler daemon...")
            
            # Initialize and start the scheduler
            scheduler = JobScheduler(pipeline, jobs_dir=args.jobs_dir)
            scheduler.start()
            
            logger.info(f"Job scheduler started and monitoring {args.jobs_dir} for job files")
            
            # Loop forever, checking for new jobs
            try:
                while True:
                    # List any active jobs for log monitoring
                    jobs = scheduler.list_jobs()
                    running_jobs = [j for j in jobs.values() if j.get('status') == 'running']
                    
                    if running_jobs:
                        logger.info(f"Currently running {len(running_jobs)} jobs")
                    
                    # Sleep for a while
                    time.sleep(60)
            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt, shutting down...")
                scheduler.stop()
                
            return 0
            
        else:
            logger.info("No catalog provided and not running in daemon mode. Use --catalog or --daemon.")
            logger.info("System initialized but exiting. Use --daemon to keep running.")
            return 0
            
    except Exception as e:
        logger.error(f"Error in main application: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
