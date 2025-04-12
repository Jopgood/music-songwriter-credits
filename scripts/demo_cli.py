#!/usr/bin/env python3
"""
Demo CLI for the songwriter identification system.
Provides a simple command-line interface to test core functionality.
"""

import os
import argparse
import logging
import csv
import json
from pathlib import Path
from typing import Dict, List, Optional
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from songwriter_id.api.musicbrainz import MusicBrainzClient
from songwriter_id.api.acoustid import AcoustIDClient
from songwriter_id.audio.fingerprinting import AudioProcessor
from songwriter_id.database.models import Base, Track, SongwriterCredit, IdentificationAttempt

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DemoApp:
    """Demo application for the songwriter identification system."""

    def __init__(self, db_url: str):
        """Initialize the demo application.

        Args:
            db_url: Database connection URL
        """
        self.db_url = db_url
        self.engine = create_engine(db_url)
        self.Session = sessionmaker(bind=self.engine)
        
        # Initialize API clients
        self.mb_client = MusicBrainzClient(
            app_name="SongwriterID",
            version="0.1.0",
            contact=os.environ.get("CONTACT_EMAIL", "admin@example.com")
        )
        
        self.acoustid_client = None
        if os.environ.get("ACOUSTID_API_KEY"):
            self.acoustid_client = AcoustIDClient(
                api_key=os.environ["ACOUSTID_API_KEY"]
            )
        
        self.audio_processor = AudioProcessor()

    def setup_database(self):
        """Set up the database schema."""
        Base.metadata.create_all(self.engine)
        logger.info("Database tables created")

    def import_catalog(self, catalog_path: str):
        """Import a catalog file into the database.

        Args:
            catalog_path: Path to the catalog CSV file
        """
        session = self.Session()
        
        try:
            logger.info(f"Importing catalog from {catalog_path}")
            with open(catalog_path, 'r', newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                
                track_count = 0
                for row in reader:
                    track = Track(
                        title=row.get('title', ''),
                        artist_name=row.get('artist', ''),
                        release_title=row.get('release', ''),
                        duration=float(row.get('duration', 0)) if row.get('duration') else None,
                        audio_path=row.get('audio_path', ''),
                        identification_status='pending'
                    )
                    session.add(track)
                    track_count += 1
                    
                    # Commit in batches to avoid memory issues
                    if track_count % 100 == 0:
                        session.commit()
                        logger.info(f"Imported {track_count} tracks...")
                
                session.commit()
                logger.info(f"Successfully imported {track_count} tracks")
        
        except Exception as e:
            session.rollback()
            logger.error(f"Error importing catalog: {e}")
        finally:
            session.close()

    def identify_track(self, track_id: int):
        """Run identification process for a single track.

        Args:
            track_id: ID of the track to identify
        """
        session = self.Session()
        
        try:
            track = session.query(Track).get(track_id)
            if not track:
                logger.error(f"Track with ID {track_id} not found")
                return
            
            logger.info(f"Identifying track: {track.title} by {track.artist_name}")
            
            # Step 1: Try MusicBrainz metadata lookup
            mb_recordings = self.mb_client.search_recording(track.title, track.artist_name)
            
            # Log the attempt
            attempt = IdentificationAttempt(
                track_id=track.track_id,
                source_used="musicbrainz",
                query_performed=f"title={track.title}, artist={track.artist_name}",
                result=json.dumps(mb_recordings[:5] if mb_recordings else [])
            )
            session.add(attempt)
            
            if mb_recordings:
                logger.info(f"Found {len(mb_recordings)} potential matches on MusicBrainz")
                
                # For demo, just use the first result
                if len(mb_recordings) > 0:
                    recording = mb_recordings[0]
                    recording_id = recording.get('id')
                    
                    if recording_id:
                        # Get songwriter credits
                        credits = self.mb_client.get_work_credits(recording_id)
                        
                        if credits:
                            logger.info(f"Found {len(credits)} songwriter credits")
                            
                            # Add credits to database
                            for credit in credits:
                                songwriter_credit = SongwriterCredit(
                                    track_id=track.track_id,
                                    songwriter_name=credit.get('name', ''),
                                    role=credit.get('role', ''),
                                    source_of_info='musicbrainz',
                                    confidence_score=0.9  # High confidence for MB matches
                                )
                                session.add(songwriter_credit)
                            
                            # Update track status
                            track.identification_status = 'identified'
                            track.confidence_score = 0.9
                            session.commit()
                            
                            return True
            
            # Step 2: If we have audio path and AcoustID configured, try audio fingerprinting
            if track.audio_path and os.path.exists(track.audio_path) and self.acoustid_client:
                logger.info(f"Trying audio fingerprinting for {track.title}")
                
                # Identify track using AcoustID
                matches = self.acoustid_client.identify_track(track.audio_path)
                
                # Log the attempt
                attempt = IdentificationAttempt(
                    track_id=track.track_id,
                    source_used="acoustid",
                    query_performed=f"audio_file={track.audio_path}",
                    result=json.dumps(matches[:5] if matches else [])
                )
                session.add(attempt)
                
                if matches:
                    logger.info(f"Found {len(matches)} matches via audio fingerprinting")
                    # Process matches similar to MB (omitted for brevity)
                    # ...
            
            # If we get here, identification failed
            logger.info(f"Could not identify songwriter credits for {track.title}")
            track.identification_status = 'manual_review'
            session.commit()
            return False
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error identifying track: {e}")
            return False
        finally:
            session.close()

    def display_track(self, track_id: int):
        """Display track details including songwriter credits.

        Args:
            track_id: ID of the track to display
        """
        session = self.Session()
        
        try:
            track = session.query(Track).get(track_id)
            if not track:
                logger.error(f"Track with ID {track_id} not found")
                return
            
            print("\n" + "=" * 50)
            print(f"Track ID: {track.track_id}")
            print(f"Title: {track.title}")
            print(f"Artist: {track.artist_name}")
            print(f"Release: {track.release_title}")
            print(f"Status: {track.identification_status}")
            print(f"Confidence: {track.confidence_score:.2f}")
            print("-" * 50)
            
            credits = session.query(SongwriterCredit).filter_by(track_id=track.track_id).all()
            if credits:
                print("Songwriter Credits:")
                for credit in credits:
                    print(f"  - {credit.songwriter_name} ({credit.role})")
                    if credit.publisher_name:
                        print(f"    Publisher: {credit.publisher_name}")
                    print(f"    Source: {credit.source_of_info}")
                    print(f"    Confidence: {credit.confidence_score:.2f}")
            else:
                print("No songwriter credits found")
            
            print("=" * 50 + "\n")
            
        except Exception as e:
            logger.error(f"Error displaying track: {e}")
        finally:
            session.close()


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description='Songwriter Identification System Demo CLI')
    parser.add_argument('--setup', action='store_true', help='Set up the database')
    parser.add_argument('--import', dest='import_path', help='Import a catalog CSV file')
    parser.add_argument('--identify', type=int, help='Identify a specific track by ID')
    parser.add_argument('--display', type=int, help='Display a track by ID')
    args = parser.parse_args()
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Get database URL from environment
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        logger.error("No database URL provided. Set DATABASE_URL environment variable.")
        return 1
    
    try:
        demo = DemoApp(db_url)
        
        if args.setup:
            demo.setup_database()
        
        if args.import_path:
            demo.import_catalog(args.import_path)
        
        if args.identify:
            demo.identify_track(args.identify)
        
        if args.display:
            demo.display_track(args.display)
            
        return 0
    except Exception as e:
        logger.error(f"Error in demo CLI: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
