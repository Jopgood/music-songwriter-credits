"""MusicBrainz database integration for songwriter identification."""

import logging
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

# Import our search and publisher modules
from songwriter_id.api.musicbrainz_db_search import (
    search_recording, 
    search_recording_advanced,
    calculate_match_score,
    get_releases_for_recording
)
from songwriter_id.api.musicbrainz_db_publishers import (
    get_work_label_relations,
    is_publisher,
    extract_publishers_from_work,
    find_work_publishers,
    get_publishers_by_recording_id,
    find_alternate_publishers,
    PUBLISHER_TYPES,
    PUBLISHER_LABEL_TYPES
)
from songwriter_id.utils.name_matching import name_similarity

logger = logging.getLogger(__name__)


class MusicBrainzDatabaseClient:
    """Client for interacting with a local MusicBrainz database."""

    # Define role mappings
    COMPOSER_ROLES = ["composer", "writer", "songwriter"]
    LYRICIST_ROLES = ["lyricist"]
    ARRANGER_ROLES = ["arranger"]
    PRODUCER_ROLES = ["producer"]

    def __init__(self, db_connection_string: str, pool_size: int = 5, max_overflow: int = 10):
        """Initialize the MusicBrainz database client.

        Args:
            db_connection_string: Database connection string for MusicBrainz DB
            pool_size: Connection pool size (default: 5)
            max_overflow: Maximum overflow connections (default: 10)
        """
        self.db_connection_string = db_connection_string

        # Create database engine with connection pooling
        self.engine = create_engine(
            db_connection_string,
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True  # Verify connections before using them
        )
        self.Session = sessionmaker(bind=self.engine)

        logger.info(
            f"Initialized MusicBrainzDatabaseClient with connection to {db_connection_string}")
        logger.info(
            f"Connection pool settings: pool_size={pool_size}, max_overflow={max_overflow}")
