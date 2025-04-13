"""Main pipeline implementation for songwriter identification."""

import json
import logging
import os
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from songwriter_id.database.models import Track, SongwriterCredit, IdentificationAttempt
from songwriter_id.data_ingestion.parser import CatalogParser
from songwriter_id.data_ingestion.normalizer import TrackNormalizer
from songwriter_id.data_ingestion.importer import CatalogImporter
from songwriter_id.api import MusicBrainzClient, AcoustIDClient

logger = logging.getLogger(__name__)


class SongwriterIdentificationPipeline:
    """Main pipeline for identifying songwriter credits."""

    def __init__(self, config_file: str, db_connection: str):
        """Initialize the pipeline with configuration.

        Args:
            config_file: Path to the configuration file
            db_connection: Database connection string
        """
        self.config_file = config_file
        self.db_connection = db_connection
        
        # Load configuration
        self.config = self._load_config(config_file)
        
        # Initialize database connection
        self.engine = create_engine(db_connection)
        self.Session = sessionmaker(bind=self.engine)
        
        # Initialize data ingestion components
        self.parser = CatalogParser(
            field_mapping=self.config.get('field_mapping', None)
        )
        self.normalizer = TrackNormalizer()
        self.importer = CatalogImporter(
            db_connection=db_connection,
            normalizer=self.normalizer
        )
        
        # Initialize API clients
        self._init_api_clients()

    def _load_config(self, config_file: str) -> Dict:
        """Load the configuration from a YAML file.
        
        Args:
            config_file: Path to the configuration file
            
        Returns:
            Configuration dictionary
        """
        config_path = Path(config_file)
        if not config_path.exists():
            logger.warning(f"Configuration file not found: {config_file}. Using default settings.")
            return {}
        
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            logger.info(f"Loaded configuration from {config_file}")
            return config
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            return {}
    
    def _init_api_clients(self):
        """Initialize API clients based on configuration."""
        # Initialize MusicBrainz client if enabled
        self.mb_client = None
        mb_config = self.config.get('apis', {}).get('musicbrainz', {})
        if mb_config.get('enabled', False):
            logger.info("Initializing MusicBrainz client")
            self.mb_client = MusicBrainzClient(
                app_name=mb_config.get('user_agent', 'SongwriterCreditsIdentifier'),
                version=mb_config.get('version', '1.0'),
                contact=mb_config.get('contact', 'contact@example.com'),
                rate_limit=mb_config.get('rate_limit', 1.0),
                retries=mb_config.get('retries', 3)
            )
        
        # Initialize AcoustID client if enabled
        self.acoustid_client = None
        acoustid_config = self.config.get('apis', {}).get('acoustid', {})
        if acoustid_config.get('enabled', False):
            logger.info("Initializing AcoustID client")
            api_key = acoustid_config.get('api_key', '')
            if api_key:
                self.acoustid_client = AcoustIDClient(api_key)
            else:
                logger.warning("AcoustID enabled but no API key provided")

    def process_catalog(self, catalog_path: str, audio_base_path: Optional[str] = None) -> Dict:
        """Process a catalog of tracks to identify songwriter credits.

        Args:
            catalog_path: Path to the catalog file (CSV or Excel)
            audio_base_path: Base path for audio files (optional)

        Returns:
            Processing statistics
        """
        logger.info(f"Processing catalog from {catalog_path}")
        
        try:
            # Step 1: Parse the catalog file
            logger.info("Step 1: Parsing catalog file")
            tracks_data = self.parser.parse_file(catalog_path, audio_base_path)
            logger.info(f"Parsed {len(tracks_data)} tracks from catalog")
            
            # Step 2: Import tracks into the database
            logger.info("Step 2: Importing tracks into database")
            tracks_added, tracks_skipped, errors = self.importer.bulk_import_tracks(
                tracks_data, 
                batch_size=self.config.get('batch_size', 100)
            )
            
            import_stats = {
                "tracks_parsed": len(tracks_data),
                "tracks_added": tracks_added,
                "tracks_skipped": tracks_skipped,
                "import_errors": len(errors)
            }
            logger.info(f"Import stats: {import_stats}")
            
            # Step 3: Process tracks through identification tiers
            logger.info("Step 3: Processing tracks through identification tiers")
            identification_stats = self._process_identification_tiers()
            
            # Combine all statistics
            stats = {
                "import": import_stats,
                "identification": identification_stats,
                "status": "completed"
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error processing catalog: {e}")
            return {"status": "failed", "error": str(e)}

    def _process_identification_tiers(self) -> Dict:
        """Process all tracks through the identification tiers.
        
        Returns:
            Identification statistics
        """
        # Get all tracks with status 'pending'
        session = self.Session()
        try:
            pending_tracks = session.query(Track).filter(
                Track.identification_status == 'pending'
            ).all()
            
            logger.info(f"Processing {len(pending_tracks)} pending tracks through identification tiers")
            
            tier1_identified = 0
            tier2_identified = 0
            tier3_identified = 0
            unidentified = 0
            
            for track in pending_tracks:
                # Process through Tier 1
                tier1_config = self.config.get('tier1', {})
                if tier1_config.get('enabled', True):
                    credits = self._tier1_metadata_identification(track)
                    if credits:
                        track.identification_status = 'identified_tier1'
                        track.confidence_score = self._evaluate_confidence(credits)
                        for credit in credits:
                            session.add(credit)
                        tier1_identified += 1
                        session.commit()
                        continue
                
                # Process through Tier 2
                tier2_config = self.config.get('tier2', {})
                if tier2_config.get('enabled', True):
                    credits = self._tier2_enhanced_matching(track)
                    if credits:
                        track.identification_status = 'identified_tier2'
                        track.confidence_score = self._evaluate_confidence(credits)
                        for credit in credits:
                            session.add(credit)
                        tier2_identified += 1
                        session.commit()
                        continue
                
                # Process through Tier 3
                tier3_config = self.config.get('tier3', {})
                if tier3_config.get('enabled', True):
                    credits = self._tier3_audio_analysis(track)
                    if credits:
                        track.identification_status = 'identified_tier3'
                        track.confidence_score = self._evaluate_confidence(credits)
                        for credit in credits:
                            session.add(credit)
                        tier3_identified += 1
                        session.commit()
                        continue
                
                # Track remains unidentified
                track.identification_status = 'manual_review'
                unidentified += 1
                session.commit()
            
            stats = {
                "tier1_identified": tier1_identified,
                "tier2_identified": tier2_identified,
                "tier3_identified": tier3_identified,
                "manual_review": unidentified,
                "total_processed": len(pending_tracks)
            }
            
            logger.info(f"Identification stats: {stats}")
            return stats
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error in identification process: {e}")
            return {"error": str(e)}
        finally:
            session.close()

    def _tier1_metadata_identification(self, track: Track) -> List[SongwriterCredit]:
        """Tier 1: Identify songwriter credits based on metadata.

        Args:
            track: Track object to process

        Returns:
            List of identified songwriter credits
        """
        logger.info(f"Tier 1: Processing track '{track.title}' by '{track.artist_name}'")
        identified_credits = []
        
        # Get configured sources for Tier 1
        tier1_sources = self.config.get('tier1', {}).get('sources', [])
        tier1_confidence_threshold = self.config.get('tier1', {}).get('confidence_threshold', 0.7)
        
        # Try MusicBrainz if enabled
        if 'musicbrainz' in tier1_sources and self.mb_client:
            mb_credits = self._try_musicbrainz_identification(track)
            
            if mb_credits:
                # Convert API credit format to SongwriterCredit objects
                for credit in mb_credits:
                    # Skip credits with low confidence
                    if credit.get('confidence_score', 0) < tier1_confidence_threshold:
                        continue
                        
                    songwriter_credit = SongwriterCredit(
                        track_id=track.track_id,
                        songwriter_name=credit['name'],
                        role=credit['role'],
                        publisher_name=credit.get('publisher_name'),
                        source_of_info=f"musicbrainz:{credit.get('source_id', '')}",
                        confidence_score=credit.get('confidence_score', 0.7)
                    )
                    identified_credits.append(songwriter_credit)
        
        # TODO: Add other PRO database integrations (ASCAP, BMI, SESAC)
        # if 'ascap' in tier1_sources and self.ascap_client:
        #    ascap_credits = self._try_ascap_identification(track)
        #    ...
        
        # Record the identification attempt
        result_text = "No results found"
        if identified_credits:
            result_text = f"Found {len(identified_credits)} credits"
            
        self._record_identification_attempt(
            track_id=track.track_id,
            source_used="tier1_metadata",
            query_performed=f"title='{track.title}', artist='{track.artist_name}'",
            result=result_text,
            confidence_score=self._evaluate_confidence(identified_credits)
        )
        
        return identified_credits
    
    def _try_musicbrainz_identification(self, track: Track) -> List[Dict]:
        """Try to identify songwriter credits using MusicBrainz.
        
        Args:
            track: Track object to process
            
        Returns:
            List of credits in API format (dicts)
        """
        logger.info(f"Trying MusicBrainz identification for '{track.title}' by '{track.artist_name}'")
        try:
            # Get songwriter credits by title and artist
            credits = self.mb_client.get_credits_by_title_artist(
                title=track.title,
                artist=track.artist_name,
                release=track.release_title
            )
            
            # Log results
            if credits:
                logger.info(f"MusicBrainz found {len(credits)} credits for '{track.title}' by '{track.artist_name}'")
                for credit in credits:
                    logger.debug(f"Credit: {credit['name']} ({credit['role']}), confidence: {credit.get('confidence_score', 0)}")
            else:
                logger.info(f"No MusicBrainz credits found for '{track.title}' by '{track.artist_name}'")
            
            # Record the identification attempt details
            self._record_identification_attempt(
                track_id=track.track_id,
                source_used="musicbrainz",
                query_performed=f"title='{track.title}', artist='{track.artist_name}', release='{track.release_title}'",
                result=json.dumps(credits) if credits else "No results found",
                confidence_score=max([c.get('confidence_score', 0) for c in credits]) if credits else 0.0
            )
            
            return credits
        except Exception as e:
            logger.error(f"Error in MusicBrainz identification: {e}")
            
            # Record the failed attempt
            self._record_identification_attempt(
                track_id=track.track_id,
                source_used="musicbrainz",
                query_performed=f"title='{track.title}', artist='{track.artist_name}', release='{track.release_title}'",
                result=f"Error: {e}",
                confidence_score=0.0
            )
            
            return []

    def _tier2_enhanced_matching(self, track: Track) -> List[SongwriterCredit]:
        """Tier 2: Identify songwriter credits using enhanced matching techniques.

        Args:
            track: Track object to process

        Returns:
            List of identified songwriter credits
        """
        logger.info(f"Tier 2: Processing track '{track.title}' by '{track.artist_name}'")
        # TODO: Implement Tier 2 identification with fuzzy matching and ML
        
        # Create a record of the identification attempt
        self._record_identification_attempt(
            track_id=track.track_id,
            source_used="tier2_enhanced",
            query_performed=f"fuzzy_match: '{track.title}', '{track.artist_name}'",
            result="No results found"
        )
        
        return []

    def _tier3_audio_analysis(self, track: Track) -> List[SongwriterCredit]:
        """Tier 3: Identify songwriter credits using audio analysis.

        Args:
            track: Track object to process

        Returns:
            List of identified songwriter credits
        """
        logger.info(f"Tier 3: Processing track '{track.title}' by '{track.artist_name}'")
        
        # Skip if no audio path is available
        if not track.audio_path:
            logger.warning(f"No audio file available for track {track.track_id}")
            return []
        
        # Skip if the audio file doesn't exist
        if not os.path.exists(track.audio_path):
            logger.warning(f"Audio file not found: {track.audio_path}")
            return []
        
        # TODO: Implement AcoustID integration for Tier 3
        
        # Create a record of the identification attempt
        self._record_identification_attempt(
            track_id=track.track_id,
            source_used="tier3_audio",
            query_performed=f"audio_fingerprint: '{track.audio_path}'",
            result="No results found"
        )
        
        return []

    def _evaluate_confidence(self, credits: List[SongwriterCredit]) -> float:
        """Evaluate the confidence score for the identified credits.

        Args:
            credits: List of songwriter credits

        Returns:
            Confidence score between 0 and 1
        """
        # Simple implementation for now
        if not credits:
            return 0.0
        
        # Average the confidence scores of individual credits
        total_confidence = sum(credit.confidence_score for credit in credits)
        return total_confidence / len(credits)
    
    def _record_identification_attempt(self, track_id: int, source_used: str, 
                                      query_performed: str, result: str, 
                                      confidence_score: float = 0.0) -> None:
        """Record an identification attempt in the database.
        
        Args:
            track_id: ID of the track
            source_used: Identification source used
            query_performed: Query string
            result: Result of the identification attempt
            confidence_score: Confidence score of the result
        """
        session = self.Session()
        try:
            attempt = IdentificationAttempt(
                track_id=track_id,
                source_used=source_used,
                query_performed=query_performed,
                result=result,
                confidence_score=confidence_score
            )
            session.add(attempt)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error recording identification attempt: {e}")
        finally:
            session.close()
