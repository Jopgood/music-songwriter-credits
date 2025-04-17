"""MusicBrainz database integration for songwriter identification - Part 2."""

import logging
from typing import Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

def get_artist_credit(session, artist_credit_id: int) -> List[Dict]:
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

def get_work_relations(session, recording_id: str) -> List[Dict]:
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

def get_artist_relations(session, recording_id: str) -> List[Dict]:
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

def get_work_by_id(session, work_id: str) -> Optional[Dict]:
    """Get detailed information about a work."""
    try:
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
        work_dict['artist-relation-list'] = get_work_artist_relations(
            session, work_id)

        # Get label relationships (publishers)
        work_dict['label-relation-list'] = get_work_label_relations(
            session, work_id)

        return work_dict
    except Exception as e:
        logger.error(f"MusicBrainz database get_work_by_id error: {e}")
        return None

def get_work_artist_relations(session, work_id: str) -> List[Dict]:
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
