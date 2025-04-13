"""MusicBrainz API integration for songwriter identification."""

import logging
import time
from typing import Dict, List, Optional, Tuple, Union

import musicbrainzngs
from urllib.error import HTTPError
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)


class MusicBrainzClient:
    """Client for interacting with the MusicBrainz API."""

    # Define role mappings
    COMPOSER_ROLES = ["composer", "writer", "songwriter"]
    LYRICIST_ROLES = ["lyricist"]
    ARRANGER_ROLES = ["arranger"]
    PRODUCER_ROLES = ["producer"]
    
    # Define publisher types
    PUBLISHER_TYPES = ["publisher", "publishing company"]

    def __init__(self, app_name: str, version: str, contact: str, rate_limit: float = 1.0, retries: int = 3):
        """Initialize the MusicBrainz client.

        Args:
            app_name: Application name for MusicBrainz
            version: Application version
            contact: Contact email
            rate_limit: Time between requests in seconds (default: 1.0)
            retries: Number of retries for failed requests (default: 3)
        """
        self.app_name = app_name
        self.rate_limit = rate_limit
        self.retries = retries
        self.last_request_time = 0
        
        # Set up MusicBrainz API
        musicbrainzngs.set_useragent(app_name, version, contact)
        musicbrainzngs.set_rate_limit(rate_limit)

    def _rate_limited_request(self, func, *args, **kwargs):
        """Execute a rate-limited request with retries.
        
        Args:
            func: Function to call
            *args: Arguments for the function
            **kwargs: Keyword arguments for the function
            
        Returns:
            Result of the function call
            
        Raises:
            Exception: If all retries fail
        """
        # Enforce rate limiting
        now = time.time()
        time_since_last = now - self.last_request_time
        if time_since_last < self.rate_limit:
            time.sleep(self.rate_limit - time_since_last)
        
        # Try the request with retries
        for attempt in range(self.retries):
            try:
                self.last_request_time = time.time()
                return func(*args, **kwargs)
            except (HTTPError, RequestException) as e:
                logger.warning(f"MusicBrainz request failed (attempt {attempt+1}/{self.retries}): {e}")
                
                # Check if we should retry based on error code
                if isinstance(e, HTTPError) and e.code in [429, 503, 504]:
                    # Rate limiting or server error - wait longer and retry
                    retry_delay = self.rate_limit * (2 ** attempt)
                    logger.info(f"Rate limited or server error, waiting {retry_delay:.2f}s before retry")
                    time.sleep(retry_delay)
                    continue
                elif attempt < self.retries - 1:
                    # Other error but not last attempt - retry after delay
                    time.sleep(self.rate_limit)
                    continue
                else:
                    raise
        
        # Should never reach here due to the raise in the loop
        raise Exception("All retry attempts failed")

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
            query = f"recording:\"{title}\" AND artist:\"{artist}\""
            result = self._rate_limited_request(
                musicbrainzngs.search_recordings,
                query=query,
                limit=limit
            )
            return result.get("recording-list", [])
        except Exception as e:
            logger.error(f"MusicBrainz search_recording error: {e}")
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
            # Build query with available parameters
            query_parts = [f'recording:"{title}"', f'artist:"{artist}"']
            if release:
                query_parts.append(f'release:"{release}"')
            
            query = " AND ".join(query_parts)
            
            result = self._rate_limited_request(
                musicbrainzngs.search_recordings,
                query=query,
                limit=limit
            )
            
            recordings = result.get("recording-list", [])
            
            # Enrich recordings with confidence scores
            scored_recordings = []
            for rec in recordings:
                # Calculate score based on similarity to search terms
                score = self._calculate_match_score(rec, title, artist, release)
                rec['score'] = score
                scored_recordings.append(rec)
            
            # Sort by score descending
            return sorted(scored_recordings, key=lambda x: x.get('score', 0), reverse=True)
            
        except Exception as e:
            logger.error(f"MusicBrainz search_recording_advanced error: {e}")
            return []
    
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
        rec_artist = recording.get('artist-credit', [{}])[0].get('artist', {}).get('name', '').lower()
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
            result = self._rate_limited_request(
                musicbrainzngs.get_recording_by_id,
                recording_id,
                includes=["artists", "releases", "work-rels", "artist-rels"]
            )
            
            return result.get("recording")
        except Exception as e:
            logger.error(f"MusicBrainz get_recording_by_id error: {e}")
            return None
    
    def get_work_by_id(self, work_id: str) -> Optional[Dict]:
        """Get detailed information about a work.

        Args:
            work_id: MusicBrainz work ID

        Returns:
            Work information or None
        """
        try:
            result = self._rate_limited_request(
                musicbrainzngs.get_work_by_id,
                work_id,
                includes=["artist-rels", "label-rels"]
            )
            
            return result.get("work")
        except Exception as e:
            logger.error(f"MusicBrainz get_work_by_id error: {e}")
            return None

    def get_work_credits(self, recording_id: str) -> List[Dict]:
        """Get songwriter credits for a work linked to a recording.

        Args:
            recording_id: MusicBrainz recording ID

        Returns:
            List of songwriter credits
        """
        try:
            # Get recording with work relationships
            recording = self._rate_limited_request(
                musicbrainzngs.get_recording_by_id,
                recording_id, 
                includes=["work-rels", "artist-rels"]
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
                        work_title = work_rel["work"].get("title", "")
                        
                        # Get work details with relationship information
                        work = self._rate_limited_request(
                            musicbrainzngs.get_work_by_id,
                            work_id, 
                            includes=["artist-rels", "label-rels"]
                        )
                        
                        if "work" in work:
                            work_data = work["work"]
                            # Extract artist relationships (composers, lyricists, etc.)
                            if "artist-relation-list" in work_data:
                                for artist_rel in work_data["artist-relation-list"]:
                                    role = artist_rel.get("type", "").lower()
                                    
                                    # Determine standardized role
                                    if role in self.COMPOSER_ROLES:
                                        standardized_role = "composer"
                                    elif role in self.LYRICIST_ROLES:
                                        standardized_role = "lyricist"
                                    elif role in self.ARRANGER_ROLES:
                                        standardized_role = "arranger"
                                    elif role in self.PRODUCER_ROLES:
                                        standardized_role = "producer"
                                    else:
                                        standardized_role = role
                                    
                                    credits.append({
                                        "name": artist_rel["artist"]["name"],
                                        "role": standardized_role,
                                        "work_title": work_title,
                                        "confidence_score": 0.9,  # High confidence for direct work credits
                                        "iswc": work_data.get("iswc"),
                                        "source": "musicbrainz",
                                        "source_id": work_id
                                    })
                            
                            # Extract publisher relationships
                            if "label-relation-list" in work_data:
                                for label_rel in work_data["label-relation-list"]:
                                    rel_type = label_rel.get("type", "").lower()
                                    if rel_type in self.PUBLISHER_TYPES:
                                        credits.append({
                                            "name": label_rel["label"]["name"],
                                            "role": "publisher",
                                            "work_title": work_title,
                                            "confidence_score": 0.9,  # High confidence for direct publishers
                                            "iswc": work_data.get("iswc"),
                                            "source": "musicbrainz",
                                            "source_id": work_id
                                        })
            
            # If no works were found, try to get composer credits directly from recording
            if not credits and "artist-relation-list" in recording_data:
                for artist_rel in recording_data["artist-relation-list"]:
                    role = artist_rel.get("type", "").lower()
                    
                    if role in self.COMPOSER_ROLES + self.LYRICIST_ROLES + self.ARRANGER_ROLES:
                        # Determine standardized role
                        if role in self.COMPOSER_ROLES:
                            standardized_role = "composer"
                        elif role in self.LYRICIST_ROLES:
                            standardized_role = "lyricist"
                        elif role in self.ARRANGER_ROLES:
                            standardized_role = "arranger"
                        else:
                            standardized_role = role
                        
                        credits.append({
                            "name": artist_rel["artist"]["name"],
                            "role": standardized_role,
                            "work_title": recording_data.get("title", ""),
                            "confidence_score": 0.7,  # Lower confidence for recording artist credits
                            "source": "musicbrainz",
                            "source_id": recording_id
                        })
            
            return credits
        except Exception as e:
            logger.error(f"MusicBrainz get_work_credits error: {e}")
            return []
    
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
            recording_id = recording.get("id")
            if not recording_id:
                continue
                
            # Get credits for this recording
            credits = self.get_work_credits(recording_id)
            
            # Adjust confidence based on recording match position
            position_factor = 1.0 if i == 0 else (0.9 if i == 1 else 0.8)
            for credit in credits:
                # Scale the confidence by position factor and recording score
                recording_score = recording.get("score", 0.5)
                credit["confidence_score"] = credit["confidence_score"] * position_factor * recording_score
                credit["recording_id"] = recording_id
                credit["recording_title"] = recording.get("title")
                
                # Also store original search terms for reference
                credit["search_title"] = title
                credit["search_artist"] = artist
                if release:
                    credit["search_release"] = release
            
            all_credits.extend(credits)
        
        # Remove duplicates (same person in same role)
        unique_credits = {}
        for credit in all_credits:
            key = f"{credit['name']}_{credit['role']}"
            # Keep the one with highest confidence
            if key not in unique_credits or credit["confidence_score"] > unique_credits[key]["confidence_score"]:
                unique_credits[key] = credit
        
        return list(unique_credits.values())
