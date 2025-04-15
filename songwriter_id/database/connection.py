"""Database connection management and verification utilities."""

import logging
import time
from typing import Optional, Tuple, Dict
import sqlalchemy
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

logger = logging.getLogger(__name__)

# Global connection status cache to prevent repeated connection attempts
# Format: {connection_string: (is_available, last_check_time, error_message)}
connection_status_cache = {}
# Cache expiration time in seconds (5 minutes)
CACHE_EXPIRATION = 300


def verify_database_connection(db_connection: str, retry_count: int = 1) -> Tuple[bool, Optional[str]]:
    """Verify that a database connection is valid.
    
    Args:
        db_connection: Database connection string
        retry_count: Number of connection attempts before giving up
    
    Returns:
        Tuple of (success, error_message)
    """
    # Check cache first to avoid repeated connection attempts
    if db_connection in connection_status_cache:
        is_available, check_time, error_message = connection_status_cache[db_connection]
        # If cache is fresh and connection was available, return cached result
        if time.time() - check_time < CACHE_EXPIRATION:
            if is_available:
                return True, None
            # For failed connections, we'll retry after 1 minute
            elif time.time() - check_time < 60:
                return False, error_message
    
    # Not in cache or cache expired, try to connect
    for attempt in range(retry_count):
        try:
            # Create a disposable engine with a short timeout
            engine = create_engine(
                db_connection, 
                connect_args={"connect_timeout": 5},
                pool_pre_ping=True
            )
            
            # Try a simple query
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            
            # If we get here, connection was successful
            logger.info(f"Successfully connected to database: {_sanitize_connection(db_connection)}")
            
            # Update cache
            connection_status_cache[db_connection] = (True, time.time(), None)
            return True, None
            
        except Exception as e:
            error_message = str(e)
            if attempt < retry_count - 1:
                # If we have more retries, wait before trying again
                logger.warning(f"Database connection attempt {attempt+1} failed. Retrying in 2 seconds. Error: {error_message}")
                time.sleep(2)
            else:
                # Final failure
                logger.error(f"Failed to connect to database after {retry_count} attempts: {_sanitize_connection(db_connection)}")
                logger.error(f"Error details: {error_message}")
                
                # Update cache with failure
                connection_status_cache[db_connection] = (False, time.time(), error_message)
                return False, error_message
    
    return False, "Unknown connection error"


def _sanitize_connection(connection_string: str) -> str:
    """Remove sensitive information from connection string for logging."""
    # This is a simple implementation that handles the most common formats
    # For production, a more robust solution might be needed
    if "://" in connection_string:
        parts = connection_string.split("://")
        if "@" in parts[1]:
            # Format: dialect://username:password@host:port/database
            auth_parts = parts[1].split("@")
            if ":" in auth_parts[0]:
                # Replace password
                user_pass = auth_parts[0].split(":")
                sanitized = f"{parts[0]}://{user_pass[0]}:******@{auth_parts[1]}"
                return sanitized
    
    # If we can't parse it or no sensitive info is found, return with partial masking
    return connection_string.split("://")[0] + "://****"


def check_all_connections(config: Dict) -> Dict[str, Tuple[bool, Optional[str]]]:
    """Check all database connections defined in configuration.
    
    Args:
        config: Configuration dictionary with database connections
        
    Returns:
        Dictionary of connection results: {connection_name: (success, error_message)}
    """
    results = {}
    
    # Check main songwriter database
    main_db = config.get('database', {}).get('connection_string', None)
    if main_db:
        results['main_database'] = verify_database_connection(main_db, retry_count=2)
    
    # Check MusicBrainz database if configured
    mb_config = config.get('apis', {}).get('musicbrainz', {})
    mb_client_type = mb_config.get('client_type', 'api')
    
    if mb_client_type == 'database' and mb_config.get('enabled', False):
        mb_db = mb_config.get('database', {}).get('connection_string', None)
        if mb_db:
            results['musicbrainz_database'] = verify_database_connection(mb_db, retry_count=2)
    
    return results
