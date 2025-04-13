"""Tests for the data ingestion module."""

import os
import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
import csv
import pandas as pd

from songwriter_id.data_ingestion.parser import CatalogParser
from songwriter_id.data_ingestion.normalizer import TrackNormalizer

class TestCatalogParser(unittest.TestCase):
    """Test cases for the CatalogParser class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.parser = CatalogParser()
        self.temp_dir = TemporaryDirectory()
        self.audio_base_path = self.temp_dir.name
    
    def tearDown(self):
        """Tear down test fixtures."""
        self.temp_dir.cleanup()
    
    def test_csv_parsing(self):
        """Test parsing a CSV file."""
        # Create a temporary CSV file
        with NamedTemporaryFile(suffix='.csv', mode='w', delete=False) as tmp_file:
            writer = csv.writer(tmp_file)
            writer.writerow(['title', 'artist_name', 'release_title', 'duration', 'audio_path'])
            writer.writerow(['Test Song', 'Test Artist', 'Test Album', '3:45', 'test.mp3'])
            writer.writerow(['Another Song', 'Another Artist', 'Another Album', '4:12', 'another.mp3'])
            tmp_path = tmp_file.name
        
        try:
            # Parse the file
            result = self.parser.parse_file(tmp_path)
            
            # Check the results
            self.assertEqual(len(result), 2)
            self.assertEqual(result[0]['title'], 'Test Song')
            self.assertEqual(result[0]['artist_name'], 'Test Artist')
            self.assertEqual(result[0]['release_title'], 'Test Album')
            self.assertEqual(result[0]['duration'], '3:45')
            self.assertEqual(result[0]['audio_path'], 'test.mp3')
            
            self.assertEqual(result[1]['title'], 'Another Song')
            self.assertEqual(result[1]['artist_name'], 'Another Artist')
        finally:
            # Clean up
            os.unlink(tmp_path)
    
    def test_field_mapping(self):
        """Test field mapping functionality."""
        # Create a temporary CSV file with non-standard columns
        with NamedTemporaryFile(suffix='.csv', mode='w', delete=False) as tmp_file:
            writer = csv.writer(tmp_file)
            writer.writerow(['Track Name', 'Artist', 'Album', 'Length', 'File'])
            writer.writerow(['Test Song', 'Test Artist', 'Test Album', '3:45', 'test.mp3'])
            tmp_path = tmp_file.name
        
        try:
            # Parse the file
            result = self.parser.parse_file(tmp_path)
            
            # Check the results
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]['title'], 'Test Song')  # Mapped from 'Track Name'
            self.assertEqual(result[0]['artist_name'], 'Test Artist')  # Mapped from 'Artist'
            self.assertEqual(result[0]['release_title'], 'Test Album')  # Mapped from 'Album'
            self.assertEqual(result[0]['duration'], '3:45')  # Mapped from 'Length'
            self.assertEqual(result[0]['audio_path'], 'test.mp3')  # Mapped from 'File'
        finally:
            # Clean up
            os.unlink(tmp_path)
    
    def test_audio_path_resolution(self):
        """Test audio path resolution."""
        # Create a temporary CSV file
        with NamedTemporaryFile(suffix='.csv', mode='w', delete=False) as tmp_file:
            writer = csv.writer(tmp_file)
            writer.writerow(['title', 'artist_name', 'audio_path'])
            writer.writerow(['Test Song', 'Test Artist', 'relative/path.mp3'])
            tmp_path = tmp_file.name
        
        try:
            # Parse the file with audio base path
            result = self.parser.parse_file(tmp_path, self.audio_base_path)
            
            # Check the results
            self.assertEqual(len(result), 1)
            expected_path = os.path.normpath(os.path.join(self.audio_base_path, 'relative/path.mp3'))
            self.assertEqual(result[0]['audio_path'], expected_path)
        finally:
            # Clean up
            os.unlink(tmp_path)


class TestTrackNormalizer(unittest.TestCase):
    """Test cases for the TrackNormalizer class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.normalizer = TrackNormalizer()
    
    def test_normalize_title(self):
        """Test title normalization."""
        test_cases = [
            # Input title, expected normalized title
            ('Test Song', 'Test Song'),
            ('  Test  Song  ', 'Test Song'),
            ('The Test Song', 'Test Song'),  # Remove leading 'The'
            ('A Test Song', 'Test Song'),    # Remove leading 'A'
            ('01 - Test Song', 'Test Song'), # Remove leading numbers
            ('Test Song (Radio Edit)', 'Test Song'),  # Remove version info
            ('Test Song [Remix]', 'Test Song'),      # Remove remix info
            ('Test Song (feat. Other Artist)', 'Test Song'),  # Remove featuring info
        ]
        
        for input_title, expected in test_cases:
            with self.subTest(input_title=input_title):
                result = self.normalizer.normalize_title(input_title)
                self.assertEqual(result, expected)
    
    def test_normalize_artist_name(self):
        """Test artist name normalization."""
        test_cases = [
            # Input artist name, expected normalized artist name
            ('Test Artist', 'Test Artist'),
            ('  Test  Artist  ', 'Test Artist'),
            ('The Test Artist', 'Test Artist'),  # Remove leading 'The'
            ('Test Artist, The', 'Test Artist'), # Remove trailing 'The'
            ('Test Artist Band', 'Test Artist'), # Remove common suffixes
            ('Test Artist feat. Other Artist', 'Test Artist feat. Other Artist'),
            ('Test Artist ft. Other Artist', 'Test Artist feat. Other Artist'),  # Standardize 'featuring'
        ]
        
        for input_name, expected in test_cases:
            with self.subTest(input_name=input_name):
                result = self.normalizer.normalize_artist_name(input_name)
                self.assertEqual(result, expected)
    
    def test_get_canonical_title(self):
        """Test canonical title extraction."""
        test_cases = [
            # Input title, expected canonical title
            ('Test Song', 'Test Song'),
            ('Test Song (Radio Edit)', 'Test Song'),
            ('Test Song [Live]', 'Test Song'),
            ('Test Song (feat. Other Artist)', 'Test Song'),
            ('Test Song (Remix) [feat. Another Artist]', 'Test Song'),
        ]
        
        for input_title, expected in test_cases:
            with self.subTest(input_title=input_title):
                result = self.normalizer.get_canonical_title(input_title)
                self.assertEqual(result, expected)
    
    def test_get_primary_artist(self):
        """Test primary artist extraction."""
        test_cases = [
            # Input artist name, expected primary artist
            ('Test Artist', 'Test Artist'),
            ('Test Artist feat. Other Artist', 'Test Artist'),
            ('Test Artist ft. Other Artist', 'Test Artist'),
            ('Test Artist & Other Artist', 'Test Artist'),
            ('Test Artist and Other Artist', 'Test Artist'),
            ('Test Artist with Other Artist', 'Test Artist'),
            ('Test Artist vs. Other Artist', 'Test Artist'),
        ]
        
        for input_name, expected in test_cases:
            with self.subTest(input_name=input_name):
                result = self.normalizer.get_primary_artist(input_name)
                self.assertEqual(result, expected)
    
    def test_normalize_track_data(self):
        """Test track data normalization."""
        track_data = {
            'title': 'The Test Song (Radio Edit)',
            'artist_name': 'The Test Artist feat. Other Artist',
            'release_title': 'Test Album (Deluxe Edition)',
        }
        
        result = self.normalizer.normalize_track_data(track_data)
        
        self.assertEqual(result['title'], 'Test Song')
        self.assertEqual(result['canonical_title'], 'Test Song')
        self.assertEqual(result['artist_name'], 'Test Artist feat. Other Artist')
        self.assertEqual(result['primary_artist'], 'Test Artist')
        self.assertEqual(result['release_title'], 'Test Album')


if __name__ == '__main__':
    unittest.main()
