"""Database setup utilities."""

import logging
import os
from sqlalchemy import create_engine, inspect, text
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
        # Total tracks
        total_tracks = session.query(Track).count()
        
        # Tracks by identification status
        pending_tracks = session.query(Track).filter_by(identification_status='pending').count()
        tier1_tracks = session.query(Track).filter_by(identification_status='identified_tier1').count()
        tier2_tracks = session.query(Track).filter_by(identification_status='identified_tier2').count()
        tier3_tracks = session.query(Track).filter_by(identification_status='identified_tier3').count()
        manual_review_tracks = session.query(Track).filter_by(identification_status='manual_review').count()
        
        # Count songwriter credits
        credits_count = session.execute(text("SELECT COUNT(*) FROM songwriter_credits")).scalar_one_or_none() or 0
        
        # Count identification attempts
        attempts_count = session.execute(text("SELECT COUNT(*) FROM identification_attempts")).scalar_one_or_none() or 0
        
        return {
            'total_tracks': total_tracks,
            'pending_tracks': pending_tracks,
            'identified_tier1': tier1_tracks,
            'identified_tier2': tier2_tracks,
            'identified_tier3': tier3_tracks,
            'manual_review': manual_review_tracks,
            'songwriter_credits': credits_count,
            'identification_attempts': attempts_count
        }
    except Exception as e:
        logger.error(f"Error getting database stats: {e}")
        return {}
