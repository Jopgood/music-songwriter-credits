"""Publisher identification functionality for MusicBrainz database integration."""

import logging
from typing import Dict, List, Optional, Set

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Define publisher types
PUBLISHER_TYPES = ["publisher", "publishing company", "original publisher"]
PUBLISHER_LABEL_TYPES = [1, 3, 4, 5, 8]  # Common label_type IDs for publishers

def get_work_label_relations(session, work_id: str) -> List[Dict]:
    """Get label (publisher) relationships for a work.

    Args:
        session: Database session
        work_id: MusicBrainz work ID

    Returns:
        List of label relation dictionaries
    """
    try:
        # Updated query to include label_type to identify publishers
        query = text("""
            SELECT
                l.id AS label_id,
                l.name AS label_name,
                lt.name AS link_type,
                lty.id AS label_type_id,
                lty.name AS label_type_name
            FROM
                l_label_work llw
            JOIN
                link lnk ON llw.link = lnk.id
            JOIN
                link_type lt ON lnk.link_type = lt.id
            JOIN
                label l ON llw.entity0 = l.id
            LEFT JOIN
                label_type lty ON l.type = lty.id
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
                    'name': row_dict['label_name'],
                    'label_type_id': row_dict['label_type_id'],
                    'label_type_name': row_dict['label_type_name']
                }
            }

            label_relations.append(relation)

        return label_relations
    except Exception as e:
        logger.error(f"Error getting work label relations: {e}")
        return []

def is_publisher(label_relation: Dict) -> bool:
    """Determine if a label relation represents a publisher.
    
    Args:
        label_relation: Label relation dictionary
        
    Returns:
        True if the label is a publisher, False otherwise
    """
    # Check if the relationship type is a publisher type
    rel_type = label_relation.get('type', '').lower()
    is_publisher_by_relation = rel_type in PUBLISHER_TYPES
    
    # Check if the label type is a publisher type
    label_info = label_relation.get('label', {})
    label_type_id = label_info.get('label_type_id')
    is_publisher_by_label_type = label_type_id in PUBLISHER_LABEL_TYPES
    
    # If either condition is met, consider this a publisher
    return is_publisher_by_relation or is_publisher_by_label_type

def extract_publishers_from_work(work: Dict, work_title: str) -> List[Dict]:
    """Extract publisher credits from a work.
    
    Args:
        work: Work dictionary with label relations
        work_title: Title of the work
        
    Returns:
        List of publisher credits
    """
    publisher_credits = []
    
    for label_rel in work.get('label-relation-list', []):
        if is_publisher(label_rel):
            label_info = label_rel.get('label', {})
            publisher_credits.append({
                'name': label_info.get('name', ''),
                'role': 'publisher',
                'work_title': work_title,
                'confidence_score': 0.9,  # High confidence for direct publishers
                'iswc': work.get('iswc'),
                'source': 'musicbrainz_db',
                'source_id': work.get('id', '')
            })
    
    return publisher_credits

def find_work_publishers(session, work_id: str, work_title: str) -> List[Dict]:
    """Find publishers for a specific work.
    
    Args:
        session: Database session
        work_id: MusicBrainz work ID
        work_title: Work title
        
    Returns:
        List of publisher credits
    """
    try:
        label_relations = get_work_label_relations(session, work_id)
        
        publisher_credits = []
        for label_rel in label_relations:
            if is_publisher(label_rel):
                label_info = label_rel.get('label', {})
                publisher_credits.append({
                    'name': label_info.get('name', ''),
                    'role': 'publisher',
                    'work_title': work_title,
                    'confidence_score': 0.9,  # High confidence for direct publishers
                    'iswc': None,  # Will be filled in later if available
                    'source': 'musicbrainz_db',
                    'source_id': work_id
                })
                
        return publisher_credits
    except Exception as e:
        logger.error(f"Error finding work publishers: {e}")
        return []

def get_publishers_by_recording_id(session, recording_id: str, works: List[Dict]) -> List[Dict]:
    """Get publisher credits for works linked to a recording.
    
    Args:
        session: Database session
        recording_id: MusicBrainz recording ID
        works: List of works linked to the recording
        
    Returns:
        List of publisher credits
    """
    publisher_credits = []
    
    for work in works:
        if 'id' in work:
            work_id = work['id']
            work_title = work.get('title', '')
            
            publishers = find_work_publishers(session, work_id, work_title)
            publisher_credits.extend(publishers)
    
    return publisher_credits

def find_alternate_publishers(session, artist_name: str, limit: int = 5) -> List[Dict]:
    """Find potential publishers associated with an artist.
    
    This is a fallback mechanism when direct publisher relations aren't found.
    
    Args:
        session: Database session
        artist_name: Name of the artist to find publishers for
        limit: Maximum number of publishers to return
        
    Returns:
        List of potential publisher credits
    """
    try:
        # This query finds labels that have published works by the artist
        query = text("""
            SELECT DISTINCT
                l.id AS label_id,
                l.name AS label_name,
                lty.id AS label_type_id,
                lty.name AS label_type_name
            FROM
                artist a
            JOIN
                l_artist_work law ON a.id = law.entity0
            JOIN
                work w ON law.entity1 = w.id
            JOIN
                l_label_work llw ON w.id = llw.entity1
            JOIN
                label l ON llw.entity0 = l.id
            LEFT JOIN
                label_type lty ON l.type = lty.id
            WHERE
                LOWER(a.name) = LOWER(:artist_name)
                AND (lty.id IN :publisher_label_types OR lty.id IS NULL)
            LIMIT :limit
        """)
        
        result = session.execute(query, {
            'artist_name': artist_name,
            'publisher_label_types': tuple(PUBLISHER_LABEL_TYPES),
            'limit': limit
        }).fetchall()
        
        publishers = []
        for row in result:
            row_dict = dict(row._mapping)
            publishers.append({
                'name': row_dict['label_name'],
                'role': 'publisher',
                'confidence_score': 0.6,  # Lower confidence for indirect publisher match
                'source': 'musicbrainz_db',
                'label_type_id': row_dict['label_type_id'],
                'label_type_name': row_dict['label_type_name']
            })
            
        return publishers
    except Exception as e:
        logger.error(f"Error finding alternate publishers: {e}")
        return []
