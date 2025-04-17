"""Tests for improved MusicBrainz database integration."""

import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy import text

from songwriter_id.utils.name_matching import normalize_name, name_similarity, create_name_variations
from songwriter_id.api.musicbrainz_db_publishers import is_publisher, extract_publishers_from_work
from songwriter_id.api.musicbrainz_db_search import calculate_match_score


class TestNameMatching(unittest.TestCase):
    """Test the name matching utilities."""

    def test_normalize_name(self):
        """Test name normalization."""
        test_cases = [
            ("Nat King Cole", "nat king cole"),
            ("Nat 'King' Cole", "nat king cole"),
            ("NAT KING COLE", "nat king cole"),
            ("Nat King Cole  ", "nat king cole"),
            ("  Nat King Cole", "nat king cole"),
            ("Nat  King  Cole", "nat king cole"),
            ("Nat (King) Cole", "nat king cole"),
            ("Nat, King Cole", "nat king cole"),
        ]

        for input_name, expected in test_cases:
            self.assertEqual(normalize_name(input_name), expected)

    def test_name_similarity(self):
        """Test name similarity calculation."""
        test_pairs = [
            ("Nat King Cole", "Nat King Cole", 1.0),  # Exact match
            ("Nat King Cole", "NAT KING COLE", 1.0),  # Case insensitive
            ("Nat King Cole", "Nat 'King' Cole", 1.0),  # With quotes
            ("Nat King Cole", "Cole, Nat King", 0.9),  # Different order
            ("Nat King Cole", "Nat King", 0.9),  # Partial match
            ("Nat King Cole", "Nathaniel Cole", 0.5),  # Different name
        ]

        for name1, name2, expected_min_similarity in test_pairs:
            similarity = name_similarity(name1, name2)
            self.assertGreaterEqual(
                similarity, expected_min_similarity,
                f"Similarity between '{name1}' and '{name2}' is {similarity}, expected at least {expected_min_similarity}"
            )

    def test_create_name_variations(self):
        """Test creating name variations for queries."""
        original = "Nat 'King' Cole"
        no_quotes, with_quotes, exact = create_name_variations(original)

        self.assertEqual(no_quotes, "Nat King Cole")
        self.assertEqual(with_quotes, "'Nat 'King' Cole'")
        self.assertEqual(exact, original)


class TestPublisherIdentification(unittest.TestCase):
    """Test the publisher identification functionality."""

    def test_is_publisher(self):
        """Test the publisher identification logic."""
        # Publisher by relationship type
        rel_type_publisher = {
            'type': 'publisher',
            'label': {
                'id': '123',
                'name': 'Test Publisher',
                'label_type_id': None
            }
        }
        self.assertTrue(is_publisher(rel_type_publisher))

        # Publisher by label type
        label_type_publisher = {
            'type': 'other relationship',
            'label': {
                'id': '123',
                'name': 'Test Publisher',
                'label_type_id': 3  # A publisher label type
            }
        }
        self.assertTrue(is_publisher(label_type_publisher))

        # Not a publisher
        not_publisher = {
            'type': 'other relationship',
            'label': {
                'id': '123',
                'name': 'Test Label',
                'label_type_id': None
            }
        }
        self.assertFalse(is_publisher(not_publisher))

    def test_extract_publishers_from_work(self):
        """Test extracting publishers from a work."""
        work = {
            'id': '123',
            'name': 'Test Work',
            'iswc': 'T-123456789-0',
            'label-relation-list': [
                {
                    'type': 'publisher',
                    'label': {
                        'id': '456',
                        'name': 'Publisher 1',
                        'label_type_id': None
                    }
                },
                {
                    'type': 'other',
                    'label': {
                        'id': '789',
                        'name': 'Publisher 2',
                        'label_type_id': 3
                    }
                },
                {
                    'type': 'other',
                    'label': {
                        'id': '012',
                        'name': 'Not Publisher',
                        'label_type_id': None
                    }
                }
            ]
        }

        publishers = extract_publishers_from_work(work, 'Work Title')
        
        # Should find 2 publishers
        self.assertEqual(len(publishers), 2)
        self.assertEqual(publishers[0]['name'], 'Publisher 1')
        self.assertEqual(publishers[0]['role'], 'publisher')
        self.assertEqual(publishers[1]['name'], 'Publisher 2')
        self.assertEqual(publishers[1]['role'], 'publisher')


class TestSearchMatching(unittest.TestCase):
    """Test the search and matching functionality."""

    def test_calculate_match_score(self):
        """Test the match score calculation."""
        recording = {
            'title': 'Unforgettable',
            'artist-credit': [
                {
                    'artist': {
                        'name': 'Nat King Cole'
                    }
                }
            ],
            'release-list': [
                {
                    'title': 'The Unforgettable Nat King Cole'
                }
            ]
        }

        # Exact match
        score1 = calculate_match_score(recording, 'Unforgettable', 'Nat King Cole', 'The Unforgettable Nat King Cole')
        # Should be very high (close to 1.0)
        self.assertGreaterEqual(score1, 0.9)

        # Similar but not exact
        score2 = calculate_match_score(recording, 'Unforgettable', 'Nat Cole', 'Unforgettable Songs')
        # Should be moderate
        self.assertGreaterEqual(score2, 0.6)
        self.assertLess(score2, score1)

        # Low similarity
        score3 = calculate_match_score(recording, 'Forget Me Not', 'Nathaniel Cole', 'Unknown Album')
        # Should be low
        self.assertLess(score3, 0.6)
        self.assertLess(score3, score2)


@patch('songwriter_id.api.musicbrainz_db.search_recording_advanced')
@patch('songwriter_id.api.musicbrainz_db.get_recording_by_id')
@patch('songwriter_id.api.musicbrainz_db.get_work_credits')
class TestClientIntegration(unittest.TestCase):
    """Tests that verify the client class functionality."""

    def test_get_credits_by_title_artist(self, mock_get_work_credits, mock_get_recording_by_id, mock_search):
        """Test getting credits by title and artist."""
        from songwriter_id.api.musicbrainz_db import MusicBrainzDatabaseClient
        
        # Mock data
        mock_search.return_value = [
            {
                'id': '123',
                'title': 'Unforgettable',
                'score': 0.95
            }
        ]
        
        mock_get_recording_by_id.return_value = {
            'id': '123',
            'title': 'Unforgettable',
            'work-relation-list': [
                {
                    'work': {
                        'id': '456',
                        'title': 'Unforgettable'
                    }
                }
            ]
        }
        
        mock_get_work_credits.return_value = [
            {
                'name': 'Irving Gordon',
                'role': 'composer',
                'confidence_score': 0.9
            },
            {
                'name': 'Sony Music Publishing',
                'role': 'publisher',
                'confidence_score': 0.9
            }
        ]
        
        # Create client with a mock session
        client = MusicBrainzDatabaseClient('mock://connection')
        client.Session = MagicMock()
        
        # Test the function
        credits = client.get_credits_by_title_artist('Unforgettable', 'Nat King Cole')
        
        # Verify results
        self.assertEqual(len(credits), 2)
        
        # Verify that the mock functions were called with expected args
        mock_search.assert_called_once()
        self.assertEqual(mock_search.call_args[0][1], 'Unforgettable')
        self.assertEqual(mock_search.call_args[0][2], 'Nat King Cole')
        
        mock_get_recording_by_id.assert_called_once_with('123')
        mock_get_work_credits.assert_called_once()


if __name__ == '__main__':
    unittest.main()
