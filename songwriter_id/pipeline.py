"""Main pipeline implementation for songwriter identification."""

import json
import logging
import os
import sys
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError

from songwriter_id.database.models import Track, SongwriterCredit, IdentificationAttempt
from songwriter_id.data_ingestion.parser import CatalogParser
from songwriter_id.data_ingestion.normalizer import TrackNormalizer
from songwriter_id.data_ingestion.importer import CatalogImporter
from songwriter_id.database.connection import verify_database_connection, check_all_connections

# Import MusicBrainz clients
from songwriter_id.api.musicbrainz import MusicBrainzClient

# Try to import database client
try:
    from songwriter_id.api.musicbrainz_db import MusicBrainzDatabaseClient
    MUSICBRAINZ_DB_AVAILABLE = True
except ImportError:
    MUSICBRAINZ_DB_AVAILABLE = False
    logging.warning(
        "MusicBrainzDatabaseClient not available. Direct database access will be disabled.")

# Make acoustid optional
try:
    from songwriter_id.api import AcoustIDClient
    ACOUSTID_AVAILABLE = True
except ImportError:
    ACOUSTID_AVAILABLE = False
    logging.warning(
        "AcoustID/Chromaprint not available. Tier 3 audio fingerprinting will be disabled.")

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
        self.connection_status = {}
        self.is_ready = False  # Flag to indicate if pipeline is ready to run

        # Load configuration
        self.config = self._load_config(config_file)

        # Verify database connections before initializing
        if not self._verify_connections():
            logger.error(
                "Database connection verification failed. Pipeline initialization incomplete.")
            return

        # Initialize database connection
        try:
            self.engine = create_engine(db_connection)
            self.Session = sessionmaker(bind=self.engine)

            # Test a simple query to verify connection
            session = self.Session()
            session.execute(text("SELECT 1"))
            session.close()

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
            api_init_success = self._init_api_clients()
            if not api_init_success:
                logger.warning(
                    "Some API clients failed to initialize, but pipeline can still operate with reduced functionality.")

            self.is_ready = True
            logger.info("Pipeline initialized successfully.")

        except Exception as e:
            logger.error(f"Error initializing pipeline: {e}")
            self.is_ready = False

    def _verify_connections(self) -> bool:
        """Verify all necessary database connections.

        Returns:
            True if all critical connections are available, False otherwise
        """
        # Check songwriter database connection (critical)
        success, error = verify_database_connection(
            self.db_connection, retry_count=2)
        self.connection_status['main_database'] = (success, error)

        if not success:
            logger.error(f"Main database connection failed: {error}")
            logger.error(
                "Pipeline cannot function without main database access.")
            return False

        # Check MusicBrainz database if configured (non-critical)
        mb_config = self.config.get('apis', {}).get('musicbrainz', {})
        mb_client_type = mb_config.get('client_type', 'api')

        if mb_client_type == 'database' and mb_config.get('enabled', False):
            mb_db = mb_config.get('database', {}).get(
                'connection_string', None)
            if mb_db:
                success, error = verify_database_connection(
                    mb_db, retry_count=2)
                self.connection_status['musicbrainz_database'] = (
                    success, error)

                if not success:
                    logger.warning(
                        f"MusicBrainz database connection failed: {error}")
                    logger.warning(
                        "Pipeline will function with reduced capabilities.")
                    # Still return True since this is non-critical

        return True

    def _load_config(self, config_file: str) -> Dict:
        """Load the configuration from a YAML file.

        Args:
            config_file: Path to the configuration file

        Returns:
            Configuration dictionary
        """
        config_path = Path(config_file)
        if not config_path.exists():
            logger.warning(
                f"Configuration file not found: {config_file}. Using default settings.")
            return {}

        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            logger.info(f"Loaded configuration from {config_file}")
            return config
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            return {}

    def _init_api_clients(self) -> bool:
        """Initialize API clients based on configuration.

        Returns:
            True if all critical clients initialized successfully
        """
        success = True

        # Initialize MusicBrainz client
        self.mb_client = None
        mb_config = self.config.get('apis', {}).get('musicbrainz', {})

        if mb_config.get('enabled', False):
            client_type = mb_config.get('client_type', 'api')

            if client_type == 'database' and MUSICBRAINZ_DB_AVAILABLE:
                # Use database client if configured and available
                db_config = mb_config.get('database', {})
                if db_config.get('enabled', True):
                    logger.info("Initializing MusicBrainz Database client")

                    # Get connection parameters from config
                    db_connection_string = db_config.get('connection_string')
                    pool_size = db_config.get('pool_size', 5)
                    max_overflow = db_config.get('max_overflow', 10)

                    if db_connection_string:
                        # Check if the connection is available
                        mb_db_success, _ = self.connection_status.get(
                            'musicbrainz_database', (False, None))

                        if mb_db_success:
                            try:
                                self.mb_client = MusicBrainzDatabaseClient(
                                    db_connection_string=db_connection_string,
                                    pool_size=pool_size,
                                    max_overflow=max_overflow
                                )
                                logger.info(
                                    "MusicBrainz database client initialized successfully.")
                            except Exception as e:
                                logger.error(
                                    f"Error initializing MusicBrainz database client: {e}")
                                success = False
                        else:
                            logger.warning(
                                "MusicBrainz database connection unavailable. Falling back to API client.")
                            client_type = 'api'  # Fall back to API client
                    else:
                        logger.error(
                            "MusicBrainz database client enabled but no connection string provided")
                        success = False

            if client_type == 'api' or (client_type == 'database' and not MUSICBRAINZ_DB_AVAILABLE) or self.mb_client is None:
                # Use API client
                if client_type == 'database' and not MUSICBRAINZ_DB_AVAILABLE:
                    logger.warning(
                        "MusicBrainzDatabaseClient not available, falling back to API client")

                api_config = mb_config.get('api', {})
                if api_config.get('enabled', True):
                    logger.info("Initializing MusicBrainz API client")
                    try:
                        self.mb_client = MusicBrainzClient(
                            app_name=api_config.get(
                                'user_agent', 'SongwriterCreditsIdentifier'),
                            version=api_config.get('version', '1.0'),
                            contact=api_config.get(
                                'contact', 'contact@example.com'),
                            rate_limit=api_config.get('rate_limit', 1.0),
                            retries=api_config.get('retries', 3)
                        )
                        logger.info(
                            "MusicBrainz API client initialized successfully.")
                    except Exception as e:
                        logger.error(
                            f"Error initializing MusicBrainz API client: {e}")
                        success = False

        # Initialize AcoustID client if enabled and available
        self.acoustid_client = None
        acoustid_config = self.config.get('apis', {}).get('acoustid', {})
        if ACOUSTID_AVAILABLE and acoustid_config.get('enabled', False):
            logger.info("Initializing AcoustID client")
            api_key = acoustid_config.get('api_key', '')
            if api_key:
                try:
                    self.acoustid_client = AcoustIDClient(api_key)
                    logger.info("AcoustID client initialized successfully.")
                except ImportError:
                    logger.warning(
                        "AcoustID client initialization failed - library not available")
                    success = False
            else:
                logger.warning("AcoustID enabled but no API key provided")
                success = False

        return success

    def process_catalog(self, catalog_path: str, audio_base_path: Optional[str] = None) -> Dict:
        """Process a catalog of tracks to identify songwriter credits.

        Args:
            catalog_path: Path to the catalog file (CSV or Excel)
            audio_base_path: Base path for audio files (optional)

        Returns:
            Processing statistics
        """
        logger.info(f"Processing catalog from {catalog_path}")

        # First check if pipeline is ready
        if not self.is_ready:
            error_msg = "Pipeline is not properly initialized. Check database connections."
            logger.error(error_msg)
            return {"status": "failed", "error": error_msg}

        # Verify connections again in case they've gone down since initialization
        if not self._verify_connections():
            error_msg = "Database connection verification failed. Cannot process catalog."
            logger.error(error_msg)
            return {"status": "failed", "error": error_msg}

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
            logger.info(
                "Step 3: Processing tracks through identification tiers")
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
            import traceback
            logger.error(traceback.format_exc())
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

            logger.info(
                f"Processing {len(pending_tracks)} pending tracks through identification tiers")

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
                        track.confidence_score = self._evaluate_confidence(
                            credits)
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
                        track.confidence_score = self._evaluate_confidence(
                            credits)
                        for credit in credits:
                            session.add(credit)
                        tier2_identified += 1
                        session.commit()
                        continue

                # Process through Tier 3
                tier3_config = self.config.get('tier3', {})
                if ACOUSTID_AVAILABLE and tier3_config.get('enabled', True):
                    credits = self._tier3_audio_analysis(track)
                    if credits:
                        track.identification_status = 'identified_tier3'
                        track.confidence_score = self._evaluate_confidence(
                            credits)
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
        logger.info(
            f"Tier 1: Processing track '{track.title}' by '{track.artist_name}'")
        identified_credits = []

        # Get configured sources for Tier 1
        tier1_sources = self.config.get('tier1', {}).get('sources', [])
        tier1_confidence_threshold = self.config.get(
            'tier1', {}).get('confidence_threshold', 0.7)

        # Try MusicBrainz if enabled
        if 'musicbrainz' in tier1_sources and self.mb_client:
            # Determine which client is being used (API or DB) for logging
            client_type = "Database" if isinstance(
                self.mb_client, MusicBrainzDatabaseClient) else "API"
            logger.info(
                f"Using MusicBrainz {client_type} client for identification")

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
        logger.info(
            f"Trying MusicBrainz identification for '{track.title}' by '{track.artist_name}'")
        try:
            # Get songwriter credits by title and artist - both client types use the same method signature
            credits = self.mb_client.get_credits_by_title_artist(
                title=track.title,
                artist=track.artist_name,
                release=track.release_title
            )

            # Log results
            if credits:
                logger.info(
                    f"MusicBrainz found {len(credits)} credits for '{track.title}' by '{track.artist_name}'")
                for credit in credits:
                    logger.debug(
                        f"Credit: {credit['name']} ({credit['role']}), confidence: {credit.get('confidence_score', 0)}")
            else:
                logger.info(
                    f"No MusicBrainz credits found for '{track.title}' by '{track.artist_name}'")

            # Determine client type for logging
            client_type = "musicbrainz_db" if isinstance(
                self.mb_client, MusicBrainzDatabaseClient) else "musicbrainz_api"

            # Record the identification attempt details
            self._record_identification_attempt(
                track_id=track.track_id,
                source_used=client_type,
                query_performed=f"title='{track.title}', artist='{track.artist_name}', release='{track.release_title}'",
                result=json.dumps(credits) if credits else "No results found",
                confidence_score=max([c.get('confidence_score', 0)
                                     for c in credits]) if credits else 0.0
            )

            return credits
        except Exception as e:
            logger.error(f"Error in MusicBrainz identification: {e}")

            # Determine client type for logging
            client_type = "musicbrainz_db" if isinstance(
                self.mb_client, MusicBrainzDatabaseClient) else "musicbrainz_api"

            # Record the failed attempt
            self._record_identification_attempt(
                track_id=track.track_id,
                source_used=client_type,
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
        logger.info(
            f"Tier 2: Processing track '{track.title}' by '{track.artist_name}'")
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
        logger.info(
            f"Tier 3: Processing track '{track.title}' by '{track.artist_name}'")

        # Skip if AcoustID is not available
        if not ACOUSTID_AVAILABLE:
            logger.warning(
                "AcoustID is not available - skipping Tier 3 processing")
            return []

        # Skip if no audio path is available
        if not track.audio_path:
            logger.warning(
                f"No audio file available for track {track.track_id}")
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

    def get_connection_status(self) -> Dict:
        """Get the status of all database connections.

        Returns:
            Dictionary of connection statuses
        """
        return self.connection_status
