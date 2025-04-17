"""MusicBrainz database integration for songwriter identification - Part 3."""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Define role mappings
COMPOSER_ROLES = ["composer", "writer", "songwriter"]
LYRICIST_ROLES = ["lyricist"]
ARRANGER_ROLES = ["arranger"]
PRODUCER_ROLES = ["producer"]

def get_work_credits(session, recording_id: str, recording: Dict, get_work_by_id, get_artist_relations) -> List[Dict]:
    """Get songwriter credits for a work linked to a recording.

    Args:
        session: Database session
        recording_id: MusicBrainz recording ID
        recording: Recording information with work relationships
        get_work_by_id: Function to get work details
        get_artist_relations: Function to get artist relations
        
    Returns:
        List of songwriter credits
    """
    if not recording:
        return []

    credits = []
    publisher_credits = []

    # Extract works
    for work_rel in recording.get('work-relation-list', []):
        if 'work' in work_rel:
            work_id = work_rel['work']['id']
            work_title = work_rel['work'].get('title', '')

            # Get work details with relationship information
            work = get_work_by_id(session, work_id)

            if work:
                # Extract artist relationships (composers, lyricists, etc.)
                for artist_rel in work.get('artist-relation-list', []):
                    role = artist_rel.get('type', '').lower()

                    # Determine standardized role
                    if role in COMPOSER_ROLES:
                        standardized_role = 'composer'
                    elif role in LYRICIST_ROLES:
                        standardized_role = 'lyricist'
                    elif role in ARRANGER_ROLES:
                        standardized_role = 'arranger'
                    elif role in PRODUCER_ROLES:
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

                # Extract publisher relationships from label relationships
                from songwriter_id.api.musicbrainz_db_publishers import extract_publishers_from_work
                publisher_credits.extend(extract_publishers_from_work(work, work_title))

    # Add publisher credits to main credits
    credits.extend(publisher_credits)

    # If no works were found, try to get composer credits directly from recording
    if not credits and 'artist-relation-list' in recording:
        for artist_rel in recording.get('artist-relation-list', []):
            role = artist_rel.get('type', '').lower()

            if role in COMPOSER_ROLES + LYRICIST_ROLES + ARRANGER_ROLES:
                # Determine standardized role
                if role in COMPOSER_ROLES:
                    standardized_role = 'composer'
                elif role in LYRICIST_ROLES:
                    standardized_role = 'lyricist'
                elif role in ARRANGER_ROLES:
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

def get_credits_by_title_artist(
    search_recording_advanced, 
    get_recording_by_id, 
    get_work_credits, 
    session,
    title: str, 
    artist: str, 
    release: Optional[str] = None
) -> List[Dict]:
    """Get songwriter credits by searching for title and artist.

    Args:
        search_recording_advanced: Function to search recordings
        get_recording_by_id: Function to get recording details
        get_work_credits: Function to get work credits
        session: Database session
        title: Track title
        artist: Artist name
        release: Release/album title (optional)

    Returns:
        List of songwriter credits
    """
    all_credits = []

    # Search for recordings
    recordings = search_recording_advanced(session, title, artist, release)

    if not recordings:
        logger.info(f"No recordings found for '{title}' by '{artist}'")
        return []

    # Process top 3 recording matches (or fewer if less available)
    for i, recording in enumerate(recordings[:3]):
        recording_id = recording.get('id')
        if not recording_id:
            continue

        # Get detailed recording information
        full_recording = get_recording_by_id(session, recording_id)
        if not full_recording:
            continue

        # Get credits for this recording
        credits = get_work_credits(session, recording_id, full_recording, 
                                    get_work_by_id=lambda s, wid: get_work_by_id(s, wid), 
                                    get_artist_relations=lambda s, rid: get_artist_relations(s, rid))

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
