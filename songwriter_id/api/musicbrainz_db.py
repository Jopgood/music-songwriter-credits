"""MusicBrainz database integration for songwriter identification."""

import logging
from typing import Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

logger = logging.getLogger(__name__)


class MusicBrainzDatabaseClient:
    """Client for interacting with a local MusicBrainz database."""

    # Define role mappings
    COMPOSER_ROLES = ["composer", "writer", "songwriter"]
    LYRICIST_ROLES = ["lyricist"]
    ARRANGER_ROLES = ["arranger"]
    PRODUCER_ROLES = ["producer"]

    # Define publisher types
    PUBLISHER_TYPES = ["publisher", "publishing company"]

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

            # Build the SQL query to match recordings
            query = text("""
                SELECT
                    r.id AS id,
                    r.name AS title,
                    r.length AS length,
                    a.id AS artist_id,
                    a.name AS artist_name,
                    ac.name AS artist_credit_name
                FROM
                    recording r
                JOIN
                    artist_credit ac ON r.artist_credit = ac.id
                JOIN
                    artist_credit_name acn ON acn.artist_credit = ac.id
                JOIN
                    artist a ON a.id = acn.artist
                WHERE
                    LOWER(r.name) LIKE LOWER(:title)
                AND
                    LOWER(a.name) LIKE LOWER(:artist)
                LIMIT :limit
            """)

            params = {
                'title': f'%{title}%',
                'artist': f'%{artist}%',
                'limit': limit
            }

            result = session.execute(query, params).fetchall()

            # Convert result to list of dictionaries
            recordings = []
            for row in result:
                recording_dict = dict(row._mapping)

                # Add artist credit in the same format as API client
                artist_credit = [{
                    'artist': {
                        'id': recording_dict.pop('artist_id'),
                        'name': recording_dict.pop('artist_name')
                    },
                    'name': recording_dict.pop('artist_credit_name')
                }]
                recording_dict['artist-credit'] = artist_credit

                # Get releases for this recording
                recording_dict['release-list'] = self._get_releases_for_recording(
                    session, recording_dict['id'])

                recordings.append(recording_dict)

            return recordings
        except Exception as e:
            logger.error(f"MusicBrainz database search_recording error: {e}")
            return []
        finally:
            session.close()

    def _get_releases_for_recording(self, session, recording_id: str) -> List[Dict]:
        """Get releases for a recording.

        Args:
            session: Database session
            recording_id: MusicBrainz recording ID

        Returns:
            List of releases
        """
        try:
            query = text("""
                SELECT
                    r.id AS id,
                    r.name AS title,
                    r.release_group AS release_group_id
                FROM
                    release r
                JOIN
                    medium m ON m.release = r.id
                JOIN
                    track t ON t.medium = m.id
                WHERE
                    t.recording = :recording_id
            """)

            result = session.execute(
                query, {'recording_id': recording_id}).fetchall()
            return [dict(row._mapping) for row in result]
        except Exception as e:
            logger.error(f"Error getting releases for recording: {e}")
            return []

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

            # Start building the query
            query_str = """
                SELECT
                    r.id AS id,
                    r.name AS title,
                    r.length AS length,
                    a.id AS artist_id,
                    a.name AS artist_name,
                    ac.name AS artist_credit_name
                FROM
                    recording r
                JOIN
                    artist_credit ac ON r.artist_credit = ac.id
                JOIN
                    artist_credit_name acn ON acn.artist_credit = ac.id
                JOIN
                    artist a ON a.id = acn.artist
            """

            params = {}
            where_clauses = []

            # Add title filter
            if title:
                where_clauses.append("LOWER(r.name) LIKE LOWER(:title)")
                params['title'] = f'%{title}%'

            # Add artist filter
            if artist:
                where_clauses.append("LOWER(a.name) LIKE LOWER(:artist)")
                params['artist'] = f'%{artist}%'

            # Add release filter if provided
            if release:
                query_str += """
                    JOIN
                        track t ON t.recording = r.id
                    JOIN
                        medium m ON t.medium = m.id
                    JOIN
                        release rel ON m.release = rel.id
                """
                where_clauses.append("LOWER(rel.name) LIKE LOWER(:release)")
                params['release'] = f'%{release}%'

            # Add WHERE clause
            if where_clauses:
                query_str += " WHERE " + " AND ".join(where_clauses)

            # Add limit
            query_str += " LIMIT :limit"
            params['limit'] = limit

            # Execute query
            query = text(query_str)
            result = session.execute(query, params).fetchall()

            # Convert result to list of dictionaries
            recordings = []
            for row in result:
                # Convert RowProxy to dict - use dict(row._mapping) instead of dict(row._mapping)
                recording_dict = dict(row._mapping)

                # Add artist credit in the same format as API client
                artist_credit = [{
                    'artist': {
                        'id': recording_dict.pop('artist_id'),
                        'name': recording_dict.pop('artist_name')
                    },
                    'name': recording_dict.pop('artist_credit_name')
                }]
                recording_dict['artist-credit'] = artist_credit

                # Get releases for this recording
                recording_dict['release-list'] = self._get_releases_for_recording(
                    session, recording_dict['id'])

                # Calculate score based on similarity to search terms
                score = self._calculate_match_score(
                    recording_dict, title, artist, release)
                recording_dict['score'] = score

                recordings.append(recording_dict)

            # Sort by score descending
            recordings.sort(key=lambda x: x.get('score', 0), reverse=True)

            return recordings
        except Exception as e:
            logger.error(
                f"MusicBrainz database search_recording_advanced error: {e}")
            return []
        finally:
            session.close()

    def _calculate_match_score(self, recording: Dict, title: str, artist: str,
                               release: Optional[str] = None) -> float:
        """Calculate a match confidence score for a recording.

        Args:
            recording: Recording data from MusicBrainz
            title: Search title
            artist: Search artist
            release: Search release/album title (optional)

        Returns:
            Confidence score between 0.0 and 1.0
        """
        score = 0.0
        title_score = 0.0
        artist_score = 0.0
        release_score = 0.0

        # Title match (max 0.5)
        rec_title = recording.get('title', '').lower()
        title_lower = title.lower()

        if rec_title == title_lower:
            title_score = 0.5
        elif title_lower in rec_title or rec_title in title_lower:
            title_score = 0.3

        # Artist match (max 0.3)
        rec_artist = recording.get(
            'artist-credit', [{}])[0].get('artist', {}).get('name', '').lower()
        artist_lower = artist.lower()

        if rec_artist == artist_lower:
            artist_score = 0.3
        elif artist_lower in rec_artist or rec_artist in artist_lower:
            artist_score = 0.2

        # Release match (max 0.2)
        if release and 'release-list' in recording:
            release_lower = release.lower()
            for rel in recording.get('release-list', []):
                rel_title = rel.get('title', '').lower()
                if rel_title == release_lower:
                    release_score = 0.2
                    break
                elif release_lower in rel_title or rel_title in release_lower:
                    release_score = 0.1
                    break
        elif not release:
            # No release to match against - give a neutral score
            release_score = 0.1

        score = title_score + artist_score + release_score
        return score

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
            recording_dict['artist-credit'] = self._get_artist_credit(
                session, artist_credit_id)

            # Get work relationships
            recording_dict['work-relation-list'] = self._get_work_relations(
                session, recording_id)

            # Get artist relationships
            recording_dict['artist-relation-list'] = self._get_artist_relations(
                session, recording_id)

            # Get releases
            recording_dict['release-list'] = self._get_releases_for_recording(
                session, recording_id)

            return recording_dict
        except Exception as e:
            logger.error(
                f"MusicBrainz database get_recording_by_id error: {e}")
            return None
        finally:
            session.close()

    def _get_artist_credit(self, session, artist_credit_id: int) -> List[Dict]:
        """Get artist credit information.

        Args:
            session: Database session
            artist_credit_id: Artist credit ID

        Returns:
            List of artist credit dictionaries
        """
        try:
            query = text("""
                SELECT
                    a.id AS artist_id,
                    a.name AS artist_name,
                    acn.name AS credit_name,
                    acn.join_phrase
                FROM
                    artist_credit_name acn
                JOIN
                    artist a ON acn.artist = a.id
                WHERE
                    acn.artist_credit = :artist_credit_id
                ORDER BY
                    acn.position
            """)

            result = session.execute(
                query, {'artist_credit_id': artist_credit_id}).fetchall()

            artist_credits = []
            for row in result:
                row_dict = dict(row._mapping)
                credit = {
                    'artist': {
                        'id': row_dict['artist_id'],
                        'name': row_dict['artist_name']
                    },
                    'name': row_dict['credit_name']
                }

                if row_dict['join_phrase']:
                    credit['joinphrase'] = row_dict['join_phrase']

                artist_credits.append(credit)

            return artist_credits
        except Exception as e:
            logger.error(f"Error getting artist credit: {e}")
            return []

    def _get_work_relations(self, session, recording_id: str) -> List[Dict]:
        """Get work relationships for a recording.

        Args:
            session: Database session
            recording_id: MusicBrainz recording ID

        Returns:
            List of work relation dictionaries
        """
        try:
            query = text("""
                SELECT
                    w.id AS work_id,
                    w.name AS work_name,
                    lt.name AS link_type,
                    l.begin_date_year, l.begin_date_month, l.begin_date_day,
                    l.end_date_year, l.end_date_month, l.end_date_day
                FROM
                    l_recording_work lrw
                JOIN
                    link l ON lrw.link = l.id
                JOIN
                    link_type lt ON l.link_type = lt.id
                JOIN
                    work w ON lrw.entity1 = w.id
                WHERE
                    lrw.entity0 = :recording_id
                ORDER BY
                    lt.name
            """)

            result = session.execute(
                query, {'recording_id': recording_id}).fetchall()

            work_relations = []
            for row in result:
                row_dict = dict(row._mapping)
                relation = {
                    'type': row_dict['link_type'],
                    'work': {
                        'id': row_dict['work_id'],
                        'title': row_dict['work_name']
                    }
                }

                # Add date information if available
                if row_dict['begin_date_year']:
                    relation['begin'] = f"{row_dict['begin_date_year']}"
                    if row_dict['begin_date_month']:
                        relation['begin'] += f"-{row_dict['begin_date_month']:02d}"
                        if row_dict['begin_date_day']:
                            relation['begin'] += f"-{row_dict['begin_date_day']:02d}"

                if row_dict['end_date_year']:
                    relation['end'] = f"{row_dict['end_date_year']}"
                    if row_dict['end_date_month']:
                        relation['end'] += f"-{row_dict['end_date_month']:02d}"
                        if row_dict['end_date_day']:
                            relation['end'] += f"-{row_dict['end_date_day']:02d}"

                work_relations.append(relation)

            return work_relations
        except Exception as e:
            logger.error(f"Error getting work relations: {e}")
            return []

    def _get_artist_relations(self, session, recording_id: str) -> List[Dict]:
        """Get artist relationships for a recording.

        Args:
            session: Database session
            recording_id: MusicBrainz recording ID

        Returns:
            List of artist relation dictionaries
        """
        try:
            query = text("""
                SELECT
                    a.id AS artist_id,
                    a.name AS artist_name,
                    lt.name AS link_type
                FROM
                    l_artist_recording lar
                JOIN
                    link l ON lar.link = l.id
                JOIN
                    link_type lt ON l.link_type = lt.id
                JOIN
                    artist a ON lar.entity0 = a.id
                WHERE
                    lar.entity1 = :recording_id
                ORDER BY
                    lt.name
            """)

            result = session.execute(
                query, {'recording_id': recording_id}).fetchall()

            artist_relations = []
            for row in result:
                row_dict = dict(row._mapping)
                relation = {
                    'type': row_dict['link_type'],
                    'artist': {
                        'id': row_dict['artist_id'],
                        'name': row_dict['artist_name']
                    }
                }

                artist_relations.append(relation)

            return artist_relations
        except Exception as e:
            logger.error(f"Error getting artist relations: {e}")
            return []

    def get_work_by_id(self, work_id: str) -> Optional[Dict]:
        """Get detailed information about a work."""
        try:
            session = self.Session()

            # Modified query to join with the iswc table
            query = text("""
                SELECT
                    w.id AS id,
                    w.name AS name,
                    w.type AS type,
                    wt.name AS type_name,
                    i.iswc AS iswc
                FROM
                    work w
                LEFT JOIN
                    work_type wt ON w.type = wt.id
                LEFT JOIN
                    iswc i ON i.work = w.id
                WHERE
                    w.id = :work_id
            """)

            result = session.execute(query, {'work_id': work_id}).fetchone()

            if not result:
                return None

            # Fix the row mapping issue
            work_dict = dict(result._mapping) if hasattr(
                result, '_mapping') else dict(result)

            # Get artist relationships (composers, lyricists, etc.)
            work_dict['artist-relation-list'] = self._get_work_artist_relations(
                session, work_id)

            # Get label relationships (publishers)
            work_dict['label-relation-list'] = self._get_work_label_relations(
                session, work_id)

            return work_dict
        except Exception as e:
            logger.error(f"MusicBrainz database get_work_by_id error: {e}")
            return None
        finally:
            session.close()

    def _get_work_artist_relations(self, session, work_id: str) -> List[Dict]:
        """Get artist relationships for a work.

        Args:
            session: Database session
            work_id: MusicBrainz work ID

        Returns:
            List of artist relation dictionaries
        """
        try:
            query = text("""
                SELECT
                    a.id AS artist_id,
                    a.name AS artist_name,
                    lt.name AS link_type
                FROM
                    l_artist_work law
                JOIN
                    link l ON law.link = l.id
                JOIN
                    link_type lt ON l.link_type = lt.id
                JOIN
                    artist a ON law.entity0 = a.id
                WHERE
                    law.entity1 = :work_id
                ORDER BY
                    lt.name
            """)

            result = session.execute(query, {'work_id': work_id}).fetchall()

            artist_relations = []
            for row in result:
                row_dict = dict(row._mapping)
                relation = {
                    'type': row_dict['link_type'],
                    'artist': {
                        'id': row_dict['artist_id'],
                        'name': row_dict['artist_name']
                    }
                }

                artist_relations.append(relation)

            return artist_relations
        except Exception as e:
            logger.error(f"Error getting work artist relations: {e}")
            return []

    def _get_work_label_relations(self, session, work_id: str) -> List[Dict]:
        """Get label (publisher) relationships for a work.

        Args:
            session: Database session
            work_id: MusicBrainz work ID

        Returns:
            List of label relation dictionaries
        """
        try:
            query = text("""
                SELECT
                    l.id AS label_id,
                    l.name AS label_name,
                    lt.name AS link_type
                FROM
                    l_label_work llw
                JOIN
                    link lnk ON llw.link = lnk.id
                JOIN
                    link_type lt ON lnk.link_type = lt.id
                JOIN
                    label l ON llw.entity0 = l.id
                WHERE
                    llw.entity1 = :work_id
                ORDER BY
                    lt.name
            """)

            result = session.execute(query, {'work_id': work_id}).fetchall()

            label_relations = []
            for row in result:
                row_dict = dict(row._mapping)
                relation = {
                    'type': row_dict['link_type'],
                    'label': {
                        'id': row_dict['label_id'],
                        'name': row_dict['label_name']
                    }
                }

                label_relations.append(relation)

            return label_relations
        except Exception as e:
            logger.error(f"Error getting work label relations: {e}")
            return []

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

            if not recording:
                return []

            credits = []

            # Extract works
            for work_rel in recording.get('work-relation-list', []):
                if 'work' in work_rel:
                    work_id = work_rel['work']['id']
                    work_title = work_rel['work'].get('title', '')

                    # Get work details with relationship information
                    work = self.get_work_by_id(work_id)

                    if work:
                        # Extract artist relationships (composers, lyricists, etc.)
                        for artist_rel in work.get('artist-relation-list', []):
                            role = artist_rel.get('type', '').lower()

                            # Determine standardized role
                            if role in self.COMPOSER_ROLES:
                                standardized_role = 'composer'
                            elif role in self.LYRICIST_ROLES:
                                standardized_role = 'lyricist'
                            elif role in self.ARRANGER_ROLES:
                                standardized_role = 'arranger'
                            elif role in self.PRODUCER_ROLES:
                                standardized_role = 'producer'
                            else:
                                standardized_role = role

                            credits.append({
                                'name': artist_rel['artist']['name'],
                                'role': standardized_role,
                                'work_title': work_title,
                                'confidence_score': 0.9,  # High confidence for direct work credits
                                'iswc': work.get('iswc'),
                                'source': 'musicbrainz_db',
                                'source_id': work_id
                            })

                        # Extract publisher relationships
                        for label_rel in work.get('label-relation-list', []):
                            rel_type = label_rel.get('type', '').lower()
                            if rel_type in self.PUBLISHER_TYPES:
                                credits.append({
                                    'name': label_rel['label']['name'],
                                    'role': 'publisher',
                                    'work_title': work_title,
                                    'confidence_score': 0.9,  # High confidence for direct publishers
                                    'iswc': work.get('iswc'),
                                    'source': 'musicbrainz_db',
                                    'source_id': work_id
                                })

            # If no works were found, try to get composer credits directly from recording
            if not credits and 'artist-relation-list' in recording:
                for artist_rel in recording.get('artist-relation-list', []):
                    role = artist_rel.get('type', '').lower()

                    if role in self.COMPOSER_ROLES + self.LYRICIST_ROLES + self.ARRANGER_ROLES:
                        # Determine standardized role
                        if role in self.COMPOSER_ROLES:
                            standardized_role = 'composer'
                        elif role in self.LYRICIST_ROLES:
                            standardized_role = 'lyricist'
                        elif role in self.ARRANGER_ROLES:
                            standardized_role = 'arranger'
                        else:
                            standardized_role = role

                        credits.append({
                            'name': artist_rel['artist']['name'],
                            'role': standardized_role,
                            'work_title': recording.get('title', ''),
                            'confidence_score': 0.7,  # Lower confidence for recording artist credits
                            'source': 'musicbrainz_db',
                            'source_id': recording_id
                        })

            return credits
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
        all_credits = []

        # Search for recordings
        recordings = self.search_recording_advanced(title, artist, release)

        if not recordings:
            logger.info(f"No recordings found for '{title}' by '{artist}'")
            return []

        # Process top 3 recording matches (or fewer if less available)
        for i, recording in enumerate(recordings[:3]):
            recording_id = recording.get('id')
            if not recording_id:
                continue

            # Get credits for this recording
            credits = self.get_work_credits(recording_id)

            # Adjust confidence based on recording match position
            position_factor = 1.0 if i == 0 else (0.9 if i == 1 else 0.8)
            for credit in credits:
                # Scale the confidence by position factor and recording score
                recording_score = recording.get('score', 0.5)
                credit['confidence_score'] = credit['confidence_score'] * \
                    position_factor * recording_score
                credit['recording_id'] = recording_id
                credit['recording_title'] = recording.get('title')

                # Also store original search terms for reference
                credit['search_title'] = title
                credit['search_artist'] = artist
                if release:
                    credit['search_release'] = release

            all_credits.extend(credits)

        # Remove duplicates (same person in same role)
        unique_credits = {}
        for credit in all_credits:
            key = f"{credit['name']}_{credit['role']}"
            # Keep the one with highest confidence
            if key not in unique_credits or credit['confidence_score'] > unique_credits[key]['confidence_score']:
                unique_credits[key] = credit

        return list(unique_credits.values())

    def get_credits_by_recording_id(self, recording_id: str) -> List[Dict]:
        """Get songwriter credits for a recording by ID.

        Args:
            recording_id: MusicBrainz recording ID

        Returns:
            List of songwriter credits
        """
        return self.get_work_credits(recording_id)
