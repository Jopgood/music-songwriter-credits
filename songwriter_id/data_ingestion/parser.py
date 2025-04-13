"""Module for parsing catalog files (CSV/Excel) containing track information."""

import csv
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Union

import pandas as pd

logger = logging.getLogger(__name__)

class CatalogParser:
    """Parser for catalog files containing track information."""

    def __init__(self, field_mapping: Optional[Dict[str, str]] = None):
        """Initialize the catalog parser.
        
        Args:
            field_mapping: Mapping of file column names to standard field names
                (e.g., {'Track Title': 'title', 'Artist': 'artist_name'})
        """
        # Default field mapping if none provided
        self.field_mapping = field_mapping or {
            'title': 'title',
            'track_title': 'title',
            'track name': 'title',
            'name': 'title',
            
            'artist': 'artist_name',
            'artist_name': 'artist_name',
            'artist name': 'artist_name',
            'performer': 'artist_name',
            
            'album': 'release_title',
            'release': 'release_title',
            'release_title': 'release_title',
            'release title': 'release_title',
            'album_title': 'release_title',
            'album title': 'release_title',
            
            'duration': 'duration',
            'length': 'duration',
            'time': 'duration',
            
            'file': 'audio_path',
            'path': 'audio_path',
            'audio': 'audio_path',
            'audio_path': 'audio_path',
            'audio path': 'audio_path',
            'file_path': 'audio_path',
            'file path': 'audio_path'
        }
    
    def parse_file(self, file_path: Union[str, Path], audio_base_path: Optional[str] = None) -> List[Dict]:
        """Parse a catalog file and return a list of track dictionaries.
        
        Args:
            file_path: Path to the catalog file (CSV or Excel)
            audio_base_path: Base path for audio files (to resolve relative paths)
        
        Returns:
            List of dictionaries, each representing a track
        """
        file_path = Path(file_path)
        logger.info(f"Parsing catalog file: {file_path}")
        
        if not file_path.exists():
            raise FileNotFoundError(f"Catalog file not found: {file_path}")
        
        file_extension = file_path.suffix.lower()
        
        if file_extension == '.csv':
            return self._parse_csv(file_path, audio_base_path)
        elif file_extension in ['.xlsx', '.xls']:
            return self._parse_excel(file_path, audio_base_path)
        else:
            raise ValueError(f"Unsupported file format: {file_extension}")
    
    def _parse_csv(self, file_path: Path, audio_base_path: Optional[str] = None) -> List[Dict]:
        """Parse a CSV catalog file.
        
        Args:
            file_path: Path to the CSV file
            audio_base_path: Base path for audio files
        
        Returns:
            List of dictionaries, each representing a track
        """
        try:
            # First, determine the delimiter by analyzing the file
            with open(file_path, 'r', newline='', encoding='utf-8-sig') as f:
                sample = f.read(4096)
                sniffer = csv.Sniffer()
                dialect = sniffer.sniff(sample)
                delimiter = dialect.delimiter
            
            # Read the CSV with the detected delimiter
            df = pd.read_csv(file_path, delimiter=delimiter, encoding='utf-8-sig')
            return self._process_dataframe(df, audio_base_path)
            
        except Exception as e:
            logger.error(f"Error parsing CSV file {file_path}: {e}")
            raise
    
    def _parse_excel(self, file_path: Path, audio_base_path: Optional[str] = None) -> List[Dict]:
        """Parse an Excel catalog file.
        
        Args:
            file_path: Path to the Excel file
            audio_base_path: Base path for audio files
        
        Returns:
            List of dictionaries, each representing a track
        """
        try:
            df = pd.read_excel(file_path)
            return self._process_dataframe(df, audio_base_path)
        except Exception as e:
            logger.error(f"Error parsing Excel file {file_path}: {e}")
            raise
    
    def _process_dataframe(self, df: pd.DataFrame, audio_base_path: Optional[str] = None) -> List[Dict]:
        """Process a dataframe and convert it to a list of track dictionaries.
        
        Args:
            df: Pandas DataFrame containing track information
            audio_base_path: Base path for audio files
        
        Returns:
            List of dictionaries, each representing a track
        """
        # Normalize column names (lowercase, strip spaces)
        df.columns = [col.lower().strip() for col in df.columns]
        
        # Map columns using field mapping
        column_mapping = {}
        for col in df.columns:
            if col in self.field_mapping:
                column_mapping[col] = self.field_mapping[col]
        
        # Rename columns based on the mapping
        if column_mapping:
            df = df.rename(columns=column_mapping)
        
        # Convert to list of dictionaries
        tracks = df.to_dict(orient='records')
        
        # Process audio paths if base path is provided
        if audio_base_path and 'audio_path' in df.columns:
            for track in tracks:
                if track.get('audio_path'):
                    track['audio_path'] = self._resolve_audio_path(
                        track['audio_path'], audio_base_path
                    )
        
        logger.info(f"Successfully parsed catalog with {len(tracks)} tracks")
        return tracks
    
    def _resolve_audio_path(self, file_path: str, base_path: str) -> str:
        """Resolve a relative audio file path to an absolute path.
        
        Args:
            file_path: Relative or absolute file path
            base_path: Base path for audio files
        
        Returns:
            Absolute file path
        """
        if os.path.isabs(file_path):
            return file_path
        
        return os.path.normpath(os.path.join(base_path, file_path))
