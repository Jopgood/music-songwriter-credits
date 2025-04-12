"""MusicBrainz API integration for songwriter identification."""

import logging
from typing import Dict, List, Optional, Tuple

import musicbrainzngs

logger = logging.getLogger(__name__)


class MusicBrainzClient:
    """Client for interacting with the MusicBrainz API."""

    def __init__(self, app_name: str, version: str, contact: str):
        """Initialize the MusicBrainz client.

        Args:
            app_name: Application name for MusicBrainz
            version: Application version
            contact: Contact email
        """
        self.app_name = app_name
        musicbrainzngs.set_useragent(app_name, version, contact)

    def search_recording(self, title: str, artist: str) -> List[Dict]:
        """Search for recordings matching the title and artist.

        Args:
            title: Track title
            artist: Artist name

        Returns:
            List of matching recordings
        """
        try:
            query = f"recording:{title} AND artist:{artist}"
            result = musicbrainzngs.search_recordings(query=query, limit=10)
            return result.get("recording-list", [])
        except musicbrainzngs.WebServiceError as e:
            logger.error(f"MusicBrainz API error: {e}")
            return []

    def get_work_credits(self, recording_id: str) -> List[Dict]:
        """Get songwriter credits for a work linked to a recording.

        Args:
            recording_id: MusicBrainz recording ID

        Returns:
            List of songwriter credits
        """
        try:
            # Get recording with work relationships
            recording = musicbrainzngs.get_recording_by_id(
                recording_id, includes=["work-rels", "artist-rels"]
            )
            
            if "recording" not in recording:
                return []
                
            recording_data = recording["recording"]
            credits = []
            
            # Extract works
            if "work-relation-list" in recording_data:
                for work_rel in recording_data["work-relation-list"]:
                    if "work" in work_rel:
                        work_id = work_rel["work"]["id"]
                        # Get work details with relationship information
                        work = musicbrainzngs.get_work_by_id(
                            work_id, includes=["artist-rels"]
                        )
                        
                        if "work" in work and "artist-relation-list" in work["work"]:
                            for artist_rel in work["work"]["artist-relation-list"]:
                                if artist_rel["type"] in ["composer", "lyricist", "writer"]:
                                    credits.append({
                                        "name": artist_rel["artist"]["name"],
                                        "role": artist_rel["type"],
                                        "source": "musicbrainz"
                                    })
            
            return credits
        except musicbrainzngs.WebServiceError as e:
            logger.error(f"MusicBrainz API error: {e}")
            return []
