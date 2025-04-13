"""Tests for the MusicBrainz integration."""

import unittest
from unittest.mock import MagicMock, patch

from songwriter_id.api.musicbrainz import MusicBrainzClient
from songwriter_id.database.models import Track, SongwriterCredit
from songwriter_id.pipeline import SongwriterIdentificationPipeline


class TestMusicBrainzClient(unittest.TestCase):
    """Test cases for the MusicBrainzClient."""

    def setUp(self):
        """Set up test fixtures."""
        self.mb_client = MusicBrainzClient(
            app_name="SongwriterCreditsTest",
            version="1.0",
            contact="test@example.com",
            rate_limit=0.01,  # Fast for tests
            retries=1
        )

    @patch('musicbrainzngs.search_recordings')
    def test_search_recording(self, mock_search):
        """Test searching for recordings."""
        # Mock the MusicBrainz response
        mock_search.return_value = {
            "recording-list": [
                {
                    "id": "test-id-1",
                    "title": "Test Song",
                    "artist-credit": [{"artist": {"name": "Test Artist"}}]
                }
            ]
        }

        # Test the method
        results = self.mb_client.search_recording("Test Song", "Test Artist")
        
        # Assertions
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "test-id-1")
        self.assertEqual(results[0]["title"], "Test Song")
        
        # Verify the mock was called correctly
        mock_search.assert_called_once()
        args, kwargs = mock_search.call_args
        self.assertTrue('Test Song' in kwargs['query'])
        self.assertTrue('Test Artist' in kwargs['query'])

    @patch('musicbrainzngs.get_recording_by_id')
    @patch('musicbrainzngs.get_work_by_id')
    def test_get_work_credits(self, mock_get_work, mock_get_recording):
        """Test getting songwriter credits for a work."""
        # Mock the recording response
        mock_get_recording.return_value = {
            "recording": {
                "id": "test-recording-id",
                "title": "Test Song",
                "work-relation-list": [
                    {
                        "work": {
                            "id": "test-work-id",
                            "title": "Test Song"
                        }
                    }
                ]
            }
        }
        
        # Mock the work response
        mock_get_work.return_value = {
            "work": {
                "id": "test-work-id",
                "title": "Test Song",
                "artist-relation-list": [
                    {
                        "type": "composer",
                        "artist": {
                            "id": "test-artist-id",
                            "name": "Test Composer"
                        }
                    },
                    {
                        "type": "lyricist",
                        "artist": {
                            "id": "test-lyricist-id",
                            "name": "Test Lyricist"
                        }
                    }
                ]
            }
        }
        
        # Test the method
        credits = self.mb_client.get_work_credits("test-recording-id")
        
        # Assertions
        self.assertEqual(len(credits), 2)
        
        # Check composer
        composer = next(c for c in credits if c["role"] == "composer")
        self.assertEqual(composer["name"], "Test Composer")
        self.assertEqual(composer["work_title"], "Test Song")
        self.assertTrue(composer["confidence_score"] > 0.5)
        
        # Check lyricist
        lyricist = next(c for c in credits if c["role"] == "lyricist")
        self.assertEqual(lyricist["name"], "Test Lyricist")
        self.assertEqual(lyricist["work_title"], "Test Song")
        self.assertTrue(lyricist["confidence_score"] > 0.5)
        
        # Verify mocks were called correctly
        mock_get_recording.assert_called_once_with("test-recording-id", includes=["work-rels", "artist-rels"])
        mock_get_work.assert_called_once_with("test-work-id", includes=["artist-rels", "label-rels"])


class TestMusicBrainzPipelineIntegration(unittest.TestCase):
    """Test cases for MusicBrainz integration in the pipeline."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create a mock pipeline with a mock MusicBrainz client
        self.pipeline = SongwriterIdentificationPipeline(
            config_file="config/pipeline.yaml",
            db_connection="sqlite:///:memory:"
        )
        
        # Replace the real MusicBrainz client with a mock
        self.pipeline.mb_client = MagicMock()
        
        # Create a test track
        self.track = Track(
            track_id=1,
            title="Test Song",
            artist_name="Test Artist",
            release_title="Test Album",
            identification_status="pending"
        )
    
    def test_tier1_musicbrainz_integration(self):
        """Test Tier 1 identification with MusicBrainz."""
        # Mock the MusicBrainz response
        self.pipeline.mb_client.get_credits_by_title_artist.return_value = [
            {
                "name": "Test Composer",
                "role": "composer",
                "work_title": "Test Song",
                "confidence_score": 0.9,
                "source": "musicbrainz",
                "source_id": "test-work-id"
            },
            {
                "name": "Test Lyricist",
                "role": "lyricist",
                "work_title": "Test Song",
                "confidence_score": 0.85,
                "source": "musicbrainz",
                "source_id": "test-work-id"
            }
        ]
        
        # Test the Tier 1 identification
        # Patch the _record_identification_attempt method to avoid DB operations
        with patch.object(self.pipeline, '_record_identification_attempt'):
            credits = self.pipeline._tier1_metadata_identification(self.track)
        
        # Assertions
        self.assertEqual(len(credits), 2)
        
        # Check if the credits were properly converted to SongwriterCredit objects
        composer = next(c for c in credits if c.role == "composer")
        self.assertEqual(composer.songwriter_name, "Test Composer")
        self.assertEqual(composer.track_id, 1)
        self.assertTrue(composer.confidence_score >= 0.8)
        
        lyricist = next(c for c in credits if c.role == "lyricist")
        self.assertEqual(lyricist.songwriter_name, "Test Lyricist")
        self.assertEqual(lyricist.track_id, 1)
        self.assertTrue(lyricist.confidence_score >= 0.8)
        
        # Verify the MusicBrainz client was called correctly
        self.pipeline.mb_client.get_credits_by_title_artist.assert_called_once_with(
            title="Test Song",
            artist="Test Artist",
            release="Test Album"
        )


if __name__ == '__main__':
    unittest.main()
