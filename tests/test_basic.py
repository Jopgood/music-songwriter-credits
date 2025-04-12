"""Basic tests for the songwriter identification system."""

import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from songwriter_id.database.models import Base, Track, SongwriterCredit
from songwriter_id.api.musicbrainz import MusicBrainzClient
from songwriter_id.api.acoustid import AcoustIDClient


class TestDatabase:
    """Test database functionality."""

    @pytest.fixture
    def engine(self):
        """Create a test database engine."""
        # Use in-memory SQLite for testing
        engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        return engine

    @pytest.fixture
    def session(self, engine):
        """Create a test database session."""
        Session = sessionmaker(bind=engine)
        session = Session()
        yield session
        session.close()

    def test_track_creation(self, session):
        """Test creating a track in the database."""
        track = Track(
            title="Test Track",
            artist_name="Test Artist",
            release_title="Test Album",
            duration=180.0,
            identification_status="pending"
        )
        session.add(track)
        session.commit()

        # Retrieve and check
        tracks = session.query(Track).all()
        assert len(tracks) == 1
        assert tracks[0].title == "Test Track"
        assert tracks[0].artist_name == "Test Artist"

    def test_songwriter_credit_relation(self, session):
        """Test track and songwriter credit relationship."""
        # Create a track
        track = Track(
            title="Test Track",
            artist_name="Test Artist",
            identification_status="pending"
        )
        session.add(track)
        session.commit()

        # Create a songwriter credit for the track
        credit = SongwriterCredit(
            track_id=track.track_id,
            songwriter_name="Test Songwriter",
            role="composer",
            source_of_info="test",
            confidence_score=0.9
        )
        session.add(credit)
        session.commit()

        # Check relationship
        retrieved_track = session.query(Track).first()
        assert len(retrieved_track.songwriter_credits) == 1
        assert retrieved_track.songwriter_credits[0].songwriter_name == "Test Songwriter"
        assert retrieved_track.songwriter_credits[0].role == "composer"


class TestMusicBrainzClient:
    """Test MusicBrainz API client."""

    @pytest.fixture
    def client(self):
        """Create a MusicBrainz client for testing."""
        return MusicBrainzClient(
            app_name="SongwriterID-Test",
            version="0.1.0",
            contact="test@example.com"
        )

    def test_client_initialization(self, client):
        """Test client initialization."""
        assert client.app_name == "SongwriterID-Test"

    @pytest.mark.skipif(not os.environ.get("RUN_EXTERNAL_API_TESTS"), 
                      reason="External API tests disabled")
    def test_search_recording(self, client):
        """Test searching for a recording (requires external API)."""
        # This test will be skipped unless RUN_EXTERNAL_API_TESTS is set
        results = client.search_recording("Imagine", "John Lennon")
        assert isinstance(results, list)
        # We don't assert on the content as it depends on the external API


if __name__ == "__main__":
    pytest.main()
