"""Database setup utilities."""

import logging
import os
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from songwriter_id.database.models import Base, Track

logger = logging.getLogger(__name__)

def setup_database(db_url=None):
    """Set up the database schema.
    
    Args:
        db_url: Database connection URL (optional, defaults to environment variable)
    
    Returns:
        Engine object
    """
    # Get database URL from arguments or environment
    db_url = db_url or os.environ.get('DATABASE_URL')
    if not db_url:
        logger.error("No database URL provided.")
        return None
    
    try:
        logger.info(f"Connecting to database: {db_url}")
        engine = create_engine(db_url)
        
        # Check if tables exist
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        
        if 'tracks' not in existing_tables:
            logger.info("Creating database tables...")
            Base.metadata.create_all(engine)
            logger.info("Database tables created successfully.")
        else:
            logger.info("Database tables already exist.")
        
        return engine
    except Exception as e:
        logger.error(f"Error setting up database: {e}")
        return None

def create_session(engine):
    """Create a database session.
    
    Args:
        engine: SQLAlchemy engine object
        
    Returns:
        Session class
    """
    if not engine:
        return None
    
    Session = sessionmaker(bind=engine)
    return Session

def get_stats(session):
    """Get database statistics.
    
    Args:
        session: SQLAlchemy session
        
    Returns:
        Dictionary of statistics
    """
    if not session:
        return {}
    
    try:
        total_tracks = session.query(Track).count()
        pending_tracks = session.query(Track).filter_by(identification_status='pending').count()
        identified_tracks = session.query(Track).filter_by(identification_status='identified').count()
        manual_review_tracks = session.query(Track).filter_by(identification_status='manual_review').count()
        
        return {
            'total_tracks': total_tracks,
            'pending_tracks': pending_tracks,
            'identified_tracks': identified_tracks,
            'manual_review_tracks': manual_review_tracks
        }
    except Exception as e:
        logger.error(f"Error getting database stats: {e}")
        return {}
