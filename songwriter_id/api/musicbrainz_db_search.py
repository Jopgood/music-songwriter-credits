"""Search functionality for MusicBrainz database integration."""

import logging
import re
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text
from songwriter_id.utils.name_matching import name_similarity, create_name_variations

logger = logging.getLogger(__name__)

def search_recording(session, title: str, artist: str, limit: int = 10) -> List[Dict]:
    """Search for recordings matching the title and artist with fuzzy matching.

    Args:
        session: Database session
        title: Track title
        artist: Artist name
        limit: Maximum number of results (default: 10)

    Returns:
        List of matching recordings
    """
    try:
        # Build the SQL query to match recordings with fuzzy matching
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
                -- Fuzzy matching with variants for both title and artist
                (LOWER(r.name) LIKE LOWER(:title)
                OR LOWER(r.name) LIKE LOWER(:title_no_quotes)
                OR LOWER(r.name) LIKE LOWER(:title_with_quotes)
                OR LOWER(r.name) = LOWER(:title_exact))
            AND
                (LOWER(a.name) LIKE LOWER(:artist)
                OR LOWER(a.name) LIKE LOWER(:artist_no_quotes)
                OR LOWER(a.name) LIKE LOWER(:artist_with_quotes)
                OR LOWER(a.name) = LOWER(:artist_exact))
            LIMIT :limit
        """)

        # Create different variations for fuzzy matching
        title_no_quotes, title_with_quotes, title_exact = create_name_variations(title)
        artist_no_quotes, artist_with_quotes, artist_exact = create_name_variations(artist)
        
        params = {
            'title': f'%{title}%',
            'title_no_quotes': f'%{title_no_quotes}%',
            'title_with_quotes': f'%{title_with_quotes}%',
            'title_exact': title_exact,
            'artist': f'%{artist}%',
            'artist_no_quotes': f'%{artist_no_quotes}%',
            'artist_with_quotes': f'%{artist_with_quotes}%',
            'artist_exact': artist_exact,
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
            recording_dict['release-list'] = get_releases_for_recording(
                session, recording_dict['id'])

            recordings.append(recording_dict)

        return recordings
    except Exception as e:
        logger.error(f"MusicBrainz database search_recording error: {e}")
        return []

def get_releases_for_recording(session, recording_id: str) -> List[Dict]:
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

def search_recording_advanced(session, title: str, artist: str, release: Optional[str] = None,
                            limit: int = 10) -> List[Dict]:
    """Advanced search for recordings with additional parameters.

    Args:
        session: Database session
        title: Track title
        artist: Artist name
        release: Release/album title (optional)
        limit: Maximum number of results (default: 10)

    Returns:
        List of matching recordings
    """
    try:
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

        # Create different variations for fuzzy matching
        if title:
            title_no_quotes, title_with_quotes, title_exact = create_name_variations(title)
            title_clause = """
                (LOWER(r.name) LIKE LOWER(:title)
                OR LOWER(r.name) LIKE LOWER(:title_no_quotes)
                OR LOWER(r.name) LIKE LOWER(:title_with_quotes)
                OR LOWER(r.name) = LOWER(:title_exact))
            """
            where_clauses.append(title_clause)
            params['title'] = f'%{title}%'
            params['title_no_quotes'] = f'%{title_no_quotes}%'
            params['title_with_quotes'] = f'%{title_with_quotes}%'
            params['title_exact'] = title_exact

        # Add artist filter with variations
        if artist:
            artist_no_quotes, artist_with_quotes, artist_exact = create_name_variations(artist)
            artist_clause = """
                (LOWER(a.name) LIKE LOWER(:artist)
                OR LOWER(a.name) LIKE LOWER(:artist_no_quotes)
                OR LOWER(a.name) LIKE LOWER(:artist_with_quotes)
                OR LOWER(a.name) = LOWER(:artist_exact))
            """
            where_clauses.append(artist_clause)
            params['artist'] = f'%{artist}%'
            params['artist_no_quotes'] = f'%{artist_no_quotes}%'
            params['artist_with_quotes'] = f'%{artist_with_quotes}%'
            params['artist_exact'] = artist_exact

        # Add release filter if provided (also with variations)
        if release:
            release_no_quotes, release_with_quotes, release_exact = create_name_variations(release)
            
            query_str += """
                JOIN
                    track t ON t.recording = r.id
                JOIN
                    medium m ON t.medium = m.id
                JOIN
                    release rel ON m.release = rel.id
            """
            release_clause = """
                (LOWER(rel.name) LIKE LOWER(:release)
                OR LOWER(rel.name) LIKE LOWER(:release_no_quotes)
                OR LOWER(rel.name) LIKE LOWER(:release_with_quotes)
                OR LOWER(rel.name) = LOWER(:release_exact))
            """
            where_clauses.append(release_clause)
            params['release'] = f'%{release}%'
            params['release_no_quotes'] = f'%{release_no_quotes}%'
            params['release_with_quotes'] = f'%{release_with_quotes}%'
            params['release_exact'] = release_exact

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
            # Convert RowProxy to dict
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
            recording_dict['release-list'] = get_releases_for_recording(
                session, recording_dict['id'])

            # Calculate score based on similarity to search terms
            score = calculate_match_score(
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

def calculate_match_score(recording: Dict, title: str, artist: str,
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
    # Get the recording details
    rec_title = recording.get('title', '')
    rec_artist = recording.get(
        'artist-credit', [{}])[0].get('artist', {}).get('name', '')

    # Use our fuzzy name similarity function instead of simple string comparisons
    title_score = name_similarity(rec_title, title) * 0.5  # Max 0.5
    artist_score = name_similarity(rec_artist, artist) * 0.3  # Max 0.3

    # Release match (max 0.2)
    release_score = 0.0
    if release and 'release-list' in recording:
        max_release_sim = 0.0
        for rel in recording.get('release-list', []):
            rel_title = rel.get('title', '')
            sim = name_similarity(rel_title, release)
            max_release_sim = max(max_release_sim, sim)
        
        release_score = max_release_sim * 0.2
    elif not release:
        # No release to match against - give a neutral score
        release_score = 0.1

    score = title_score + artist_score + release_score
    return score
