"""Module for importing catalog data into the database."""

import logging
from typing import Dict, List, Optional, Tuple, Union

from sqlalchemy import create_engine, or_
from sqlalchemy.orm import Session, sessionmaker

from songwriter_id.database.models import Track
from songwriter_id.data_ingestion.normalizer import TrackNormalizer

logger = logging.getLogger(__name__)

class CatalogImporter:
    """Importer for adding catalog data to the database."""

    def __init__(self, db_connection: str, normalizer: Optional[TrackNormalizer] = None):
        """Initialize the catalog importer.
        
        Args:
            db_connection: Database connection string
            normalizer: Optional track normalizer instance
        """
        self.db_connection = db_connection
        self.engine = create_engine(db_connection)
        self.Session = sessionmaker(bind=self.engine)
        self.normalizer = normalizer or TrackNormalizer()
    
    def import_tracks(self, tracks_data: List[Dict]) -> Tuple[int, int, List[str]]:
        """Import a list of track dictionaries into the database.
        
        Args:
            tracks_data: List of track dictionaries
        
        Returns:
            Tuple containing (tracks_added, tracks_skipped, error_messages)
        """
        tracks_added = 0
        tracks_skipped = 0
        errors = []
        
        logger.info(f"Importing {len(tracks_data)} tracks into the database")
        
        session = self.Session()
        try:
            for track_data in tracks_data:
                try:
                    # Skip tracks without required fields
                    if not self._validate_track_data(track_data):
                        tracks_skipped += 1
                        errors.append(f"Skipped track: Missing required fields in {track_data}")
                        continue
                    
                    # Normalize the track data
                    normalized_data = self.normalizer.normalize_track_data(track_data)
                    
                    # Check if track already exists by ISRC or title+artist
                    existing_track = self._find_existing_track(
                        session, 
                        normalized_data.get('track_isrc'),
                        normalized_data['title'],
                        normalized_data['artist_name']
                    )
                    
                    if existing_track:
                        # Update the existing track with new data if needed
                        self._update_track(existing_track, normalized_data)
                        tracks_skipped += 1
                    else:
                        # Create a new track
                        track = self._create_track(normalized_data)
                        session.add(track)
                        tracks_added += 1
                
                except Exception as e:
                    tracks_skipped += 1
                    error_msg = f"Error processing track: {e} - Data: {track_data}"
                    logger.error(error_msg)
                    errors.append(error_msg)
            
            # Commit changes to the database
            session.commit()
            logger.info(f"Import complete: {tracks_added} tracks added, {tracks_skipped} tracks skipped")
            
            return tracks_added, tracks_skipped, errors
            
        except Exception as e:
            session.rollback()
            error_msg = f"Database error during import: {e}"
            logger.error(error_msg)
            errors.append(error_msg)
            return 0, len(tracks_data), errors
            
        finally:
            session.close()
    
    def bulk_import_tracks(self, tracks_data: List[Dict], batch_size: int = 100) -> Tuple[int, int, List[str]]:
        """Import tracks in batches for improved performance.
        
        Args:
            tracks_data: List of track dictionaries
            batch_size: Number of tracks to process in each batch
        
        Returns:
            Tuple containing (tracks_added, tracks_skipped, error_messages)
        """
        total_added = 0
        total_skipped = 0
        all_errors = []
        
        logger.info(f"Bulk importing {len(tracks_data)} tracks in batches of {batch_size}")
        
        # Process tracks in batches
        for i in range(0, len(tracks_data), batch_size):
            batch = tracks_data[i:i+batch_size]
            added, skipped, errors = self.import_tracks(batch)
            
            total_added += added
            total_skipped += skipped
            all_errors.extend(errors)
            
            logger.info(f"Batch {i//batch_size + 1} complete: {added} added, {skipped} skipped")
        
        logger.info(f"Bulk import complete: {total_added} tracks added, {total_skipped} tracks skipped")
        return total_added, total_skipped, all_errors
    
    def _validate_track_data(self, track_data: Dict) -> bool:
        """Validate that a track has all required fields.
        
        Args:
            track_data: Track data dictionary
        
        Returns:
            True if the track data is valid, False otherwise
        """
        # Check for required fields (title and artist_name)
        required_fields = ['title', 'artist_name']
        for field in required_fields:
            if field not in track_data or not track_data[field]:
                logger.warning(f"Missing required field '{field}' in track data")
                return False
        
        return True
    
    def _find_existing_track(self, session: Session, isrc: Optional[str] = None, 
                          title: Optional[str] = None, artist_name: Optional[str] = None) -> Optional[Track]:
        """Find an existing track in the database by ISRC or title+artist.
        
        Args:
            session: Database session
            isrc: ISRC code (optional)
            title: Track title (normalized, optional if isrc provided)
            artist_name: Artist name (normalized, optional if isrc provided)
        
        Returns:
            Track object if found, None otherwise
        """
        # First try to find by ISRC if provided (most reliable identifier)
        if isrc:
            track = session.query(Track).filter(Track.track_isrc == isrc).first()
            if track:
                return track
        
        # If no ISRC or no match by ISRC, try title and artist
        if title and artist_name:
            # Try exact match first
            track = session.query(Track).filter(
                Track.title == title,
                Track.artist_name == artist_name
            ).first()
            
            # If not found, try case-insensitive match
            if not track:
                track = session.query(Track).filter(
                    Track.title.ilike(f"%{title}%"),
                    Track.artist_name.ilike(f"%{artist_name}%")
                ).first()
            
            return track
        
        return None
    
    def _create_track(self, track_data: Dict) -> Track:
        """Create a new Track object from track data.
        
        Args:
            track_data: Track data dictionary
        
        Returns:
            New Track object
        """
        # Extract fields relevant to the Track model
        track_fields = {
            'title': track_data.get('title', ''),
            'artist_name': track_data.get('artist_name', ''),
            'track_isrc': track_data.get('track_isrc'),
            'release_title': track_data.get('release_title'),
            'duration': track_data.get('duration'),
            'audio_path': track_data.get('audio_path'),
            'identification_status': 'pending',
            'confidence_score': 0.0
        }
        
        # Create the Track object
        return Track(**track_fields)
    
    def _update_track(self, track: Track, track_data: Dict) -> None:
        """Update an existing Track object with new data.
        
        Args:
            track: Existing Track object
            track_data: New track data dictionary
        """
        # Only update fields that exist in the track_data and aren't None
        # Don't overwrite existing data with empty values
        if 'release_title' in track_data and track_data['release_title'] and not track.release_title:
            track.release_title = track_data['release_title']
            
        if 'duration' in track_data and track_data['duration'] and not track.duration:
            track.duration = track_data['duration']
            
        if 'audio_path' in track_data and track_data['audio_path'] and not track.audio_path:
            track.audio_path = track_data['audio_path']
            
        # Add ISRC if not already present
        if 'track_isrc' in track_data and track_data['track_isrc'] and not track.track_isrc:
            track.track_isrc = track_data['track_isrc']
