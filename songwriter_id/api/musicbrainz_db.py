"""MusicBrainz database integration for songwriter identification."""

import logging
from typing import Dict, List, Optional

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
# Import helper functions
from songwriter_id.api.musicbrainz_db_part2 import (
    get_artist_credit,
    get_work_relations,
    get_artist_relations,
    get_work_by_id,
    get_work_artist_relations
)
# Import credit processing
from songwriter_id.api.musicbrainz_db_part3 import (
    get_work_credits,
    get_credits_by_title_artist,
    COMPOSER_ROLES,
    LYRICIST_ROLES,
    ARRANGER_ROLES,
    PRODUCER_ROLES
)

logger = logging.getLogger(__name__)


class MusicBrainzDatabaseClient:
    """Client for interacting with a local MusicBrainz database."""

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

        # Set up role mappings from constants
        self.COMPOSER_ROLES = COMPOSER_ROLES
        self.LYRICIST_ROLES = LYRICIST_ROLES
        self.ARRANGER_ROLES = ARRANGER_ROLES
        self.PRODUCER_ROLES = PRODUCER_ROLES
        self.PUBLISHER_TYPES = PUBLISHER_TYPES
        self.PUBLISHER_LABEL_TYPES = PUBLISHER_LABEL_TYPES

        logger.info(
            f"Initialized MusicBrainzDatabaseClient with connection to {db_connection_string}")
        logger.info(
            f"Connection pool settings: pool_size={pool_size}, max_overflow={max_overflow}")

    def search_recording(self, title: str, artist: str, limit: int = 10) -> List[Dict]:
        """Search for recordings matching the title and artist.

        Args:
            title: Track title
            artist: Artist name
            limit: Maximum number of results (default: 10)

        Returns:
            List of matching recordings
        """
        try:
            session = self.Session()
            return search_recording(session, title, artist, limit)
        except Exception as e:
            logger.error(f"MusicBrainz database search_recording error: {e}")
            return []
        finally:
            session.close()

    def search_recording_advanced(self, title: str, artist: str, release: Optional[str] = None,
                                  limit: int = 10) -> List[Dict]:
        """Advanced search for recordings with additional parameters.

        Args:
            title: Track title
            artist: Artist name
            release: Release/album title (optional)
            limit: Maximum number of results (default: 10)

        Returns:
            List of matching recordings
        """
        try:
            session = self.Session()
            return search_recording_advanced(session, title, artist, release, limit)
        except Exception as e:
            logger.error(f"MusicBrainz database search_recording_advanced error: {e}")
            return []
        finally:
            session.close()

    def get_recording_by_id(self, recording_id: str) -> Optional[Dict]:
        """Get detailed information about a recording.

        Args:
            recording_id: MusicBrainz recording ID

        Returns:
            Recording information or None
        """
        try:
            session = self.Session()

            # Query recording details
            query = text("""
                SELECT
                    r.id AS id,
                    r.name AS title,
                    r.length AS length,
                    r.artist_credit AS artist_credit_id
                FROM
                    recording r
                WHERE
                    r.id = :recording_id
            """)

            result = session.execute(
                query, {'recording_id': recording_id}).fetchone()

            if not result:
                return None

            recording_dict = dict(result._mapping)

            # Get artist credit
            artist_credit_id = recording_dict.pop('artist_credit_id')
            recording_dict['artist-credit'] = get_artist_credit(
                session, artist_credit_id)

            # Get work relationships
            recording_dict['work-relation-list'] = get_work_relations(
                session, recording_id)

            # Get artist relationships
            recording_dict['artist-relation-list'] = get_artist_relations(
                session, recording_id)

            # Get releases
            recording_dict['release-list'] = get_releases_for_recording(
                session, recording_id)

            return recording_dict
        except Exception as e:
            logger.error(f"MusicBrainz database get_recording_by_id error: {e}")
            return None
        finally:
            session.close()

    def get_work_by_id(self, work_id: str) -> Optional[Dict]:
        """Get detailed information about a work."""
        try:
            session = self.Session()
            return get_work_by_id(session, work_id)
        except Exception as e:
            logger.error(f"MusicBrainz database get_work_by_id error: {e}")
            return None
        finally:
            session.close()

    def get_work_credits(self, recording_id: str) -> List[Dict]:
        """Get songwriter credits for a work linked to a recording.

        Args:
            recording_id: MusicBrainz recording ID

        Returns:
            List of songwriter credits
        """
        try:
            session = self.Session()

            # Get recording info with work relationships
            recording = self.get_recording_by_id(recording_id)
            
            return get_work_credits(
                session, 
                recording_id, 
                recording, 
                get_work_by_id=get_work_by_id,
                get_artist_relations=get_artist_relations
            )
        except Exception as e:
            logger.error(f"MusicBrainz database get_work_credits error: {e}")
            return []
        finally:
            session.close()

    def get_credits_by_title_artist(self, title: str, artist: str, release: Optional[str] = None) -> List[Dict]:
        """Get songwriter credits by searching for title and artist.

        Args:
            title: Track title
            artist: Artist name
            release: Release/album title (optional)

        Returns:
            List of songwriter credits
        """
        try:
            session = self.Session()
            
            return get_credits_by_title_artist(
                search_recording_advanced,
                self.get_recording_by_id,
                get_work_credits,
                session,
                title,
                artist,
                release
            )
        except Exception as e:
            logger.error(f"Error in get_credits_by_title_artist: {e}")
            return []
        finally:
            session.close()

    def get_credits_by_recording_id(self, recording_id: str) -> List[Dict]:
        """Get songwriter credits for a recording by ID.

        Args:
            recording_id: MusicBrainz recording ID

        Returns:
            List of songwriter credits
        """
        return self.get_work_credits(recording_id)
