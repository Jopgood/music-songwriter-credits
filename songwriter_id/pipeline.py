"""Main pipeline implementation for songwriter identification."""

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
        
        # Initialize components
        self.parser = CatalogParser(
            field_mapping=self.config.get('field_mapping', None)
        )
        self.normalizer = TrackNormalizer()
        self.importer = CatalogImporter(
            db_connection=db_connection,
            normalizer=self.normalizer
        )

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
                credits = self._tier1_metadata_identification(track)
                if credits:
                    track.identification_status = 'identified_tier1'
                    track.confidence_score = self._evaluate_confidence(credits)
                    for credit in credits:
                        session.add(credit)
                    tier1_identified += 1
                    continue
                
                # Process through Tier 2
                credits = self._tier2_enhanced_matching(track)
                if credits:
                    track.identification_status = 'identified_tier2'
                    track.confidence_score = self._evaluate_confidence(credits)
                    for credit in credits:
                        session.add(credit)
                    tier2_identified += 1
                    continue
                
                # Process through Tier 3
                credits = self._tier3_audio_analysis(track)
                if credits:
                    track.identification_status = 'identified_tier3'
                    track.confidence_score = self._evaluate_confidence(credits)
                    for credit in credits:
                        session.add(credit)
                    tier3_identified += 1
                    continue
                
                # Track remains unidentified
                track.identification_status = 'manual_review'
                unidentified += 1
            
            # Commit changes
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
        # TODO: Implement Tier 1 identification with MusicBrainz and other metadata sources
        
        # Create a record of the identification attempt
        self._record_identification_attempt(
            track_id=track.track_id,
            source_used="tier1_metadata",
            query_performed=f"title='{track.title}', artist='{track.artist_name}'",
            result="No results found"
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
        
        # TODO: Implement Tier 3 identification with audio fingerprinting
        
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
