"""Module for normalizing track and artist names to standardized formats."""

import logging
import re
import unicodedata
from typing import Dict, Optional, Union

logger = logging.getLogger(__name__)

class TrackNormalizer:
    """Normalizer for track and artist names to standardize formats."""

    def __init__(self):
        """Initialize the track normalizer."""
        # Common patterns to normalize
        self.patterns = {
            'featuring': [r'feat\.?\s+', r'featuring\s+', r'ft\.?\s+', r'\(with\s+'],
            'version': [r'\(([^()]*?version[^()]*?)\)', r'\[([^[\]]*?version[^[\]]*?)\]'],
            'remix': [r'\(([^()]*?remix[^()]*?)\)', r'\[([^[\]]*?remix[^[\]]*?)\]'],
            'remaster': [r'\(([^()]*?remaster[^()]*?)\)', r'\[([^[\]]*?remaster[^[\]]*?)\]',
                         r'\(([^()]*?remastered[^()]*?)\)', r'\[([^[\]]*?remastered[^[\]]*?)\]'],
            'live': [r'\(([^()]*?live[^()]*?)\)', r'\[([^[\]]*?live[^[\]]*?)\]'],
            'demo': [r'\(([^()]*?demo[^()]*?)\)', r'\[([^[\]]*?demo[^[\]]*?)\]'],
            'radio_edit': [r'\(([^()]*?radio[^()]*?edit[^()]*?)\)', r'\[([^[\]]*?radio[^[\]]*?edit[^[\]]*?)\]'],
            'extended': [r'\(([^()]*?extended[^()]*?)\)', r'\[([^[\]]*?extended[^[\]]*?)\]'],
            'album_version': [r'\(([^()]*?album[^()]*?version[^()]*?)\)', r'\[([^[\]]*?album[^[\]]*?version[^[\]]*?)\]'],
        }
        
        # Deterministic replacement for certain characters (beyond 
        # basic Unicode normalization)
        self.char_replacements = {
            ''': "'",    # curly apostrophe to straight
            ''': "'",    # another curly apostrophe
            '"': '"',    # curly quote to straight
            '"': '"',    # another curly quote
            '…': '...',  # ellipsis to three dots
            '—': '-',    # em dash to hyphen
            '–': '-',    # en dash to hyphen
            '−': '-',    # minus sign to hyphen
            '･': '.',    # full-width dot to regular dot
            '！': '!',    # full-width exclamation to regular
            '？': '?',    # full-width question mark to regular
            '（': '(',    # full-width parentheses to regular
            '）': ')',    
            '［': '[',    # full-width brackets to regular
            '］': ']',
            '：': ':',    # full-width colon to regular
            '；': ';',    # full-width semicolon to regular
            '，': ',',    # full-width comma to regular
        }
        
        # Composite artist name separators
        self.artist_separators = [
            ' & ', ' and ', ' feat. ', ' feat ', ' featuring ', ' ft. ', ' ft ', 
            ' with ', ' vs. ', ' vs ', ' versus ', ' x '
        ]
        
    def normalize_track_data(self, track_data: Dict) -> Dict:
        """Normalize track data dictionary.
        
        Args:
            track_data: Dictionary containing track information
        
        Returns:
            Normalized track data dictionary
        """
        normalized_data = track_data.copy()
        
        # Normalize the title if present
        if 'title' in normalized_data and normalized_data['title']:
            normalized_data['title'] = self.normalize_title(normalized_data['title'])
            
            # Add a field for canonical title (without version/remix info)
            normalized_data['canonical_title'] = self.get_canonical_title(normalized_data['title'])
        
        # Normalize the artist name if present
        if 'artist_name' in normalized_data and normalized_data['artist_name']:
            normalized_data['artist_name'] = self.normalize_artist_name(normalized_data['artist_name'])
            
            # Add primary artist (without features)
            normalized_data['primary_artist'] = self.get_primary_artist(normalized_data['artist_name'])
        
        # Normalize the release title if present
        if 'release_title' in normalized_data and normalized_data['release_title']:
            normalized_data['release_title'] = self.normalize_title(normalized_data['release_title'])
            
        # Normalize ISRC if present
        if 'isrc' in normalized_data and normalized_data['isrc']:
            normalized_data['isrc'] = self.normalize_isrc(normalized_data['isrc'])
        
        return normalized_data
    
    def normalize_text(self, text: str) -> str:
        """Basic text normalization applying to all fields.
        
        Args:
            text: Text to normalize
        
        Returns:
            Normalized text
        """
        if not text:
            return ""
        
        # Convert to string if not already
        text = str(text).strip()
        
        # Unicode normalization (NFKD: compatibility decomposition)
        text = unicodedata.normalize('NFKD', text)
        
        # Apply character replacements
        for old, new in self.char_replacements.items():
            text = text.replace(old, new)
        
        # Remove consecutive spaces
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def normalize_title(self, title: str) -> str:
        """Normalize a track title.
        
        Args:
            title: Track title to normalize
        
        Returns:
            Normalized track title
        """
        title = self.normalize_text(title)
        
        # Remove leading "The ", "A ", "An " with parentheses
        title = re.sub(r'^(The|A|An)\s+', '', title)
        
        # Remove common junk or placeholder text
        junk_patterns = [
            r'^\d+\s*[\-\.\)]\s*',  # Leading numbers (e.g., "1. ", "2 - ", "3) ")
            r'^\[.{1,5}\]\s*',      # Short bracketed text (e.g., "[WIP] ")
            r'^\*.+\*\s*',          # Starred text (e.g., "*explicit* ")
        ]
        
        for pattern in junk_patterns:
            title = re.sub(pattern, '', title)
        
        return title.strip()
    
    def normalize_artist_name(self, artist_name: str) -> str:
        """Normalize an artist name.
        
        Args:
            artist_name: Artist name to normalize
        
        Returns:
            Normalized artist name
        """
        artist_name = self.normalize_text(artist_name)
        
        # Standardize "featuring" notation
        for pattern in self.patterns['featuring']:
            artist_name = re.sub(pattern, " feat. ", artist_name, flags=re.IGNORECASE)
        
        # Normalize "The" prefixes
        artist_name = re.sub(r'^The\s+', '', artist_name)
        artist_name = re.sub(r',\s+The$', '', artist_name)
        
        # Remove common suffixes like "Band", "Orchestra", etc.
        common_suffixes = [
            r'\s+Band$', r'\s+Orchestra$', r'\s+Ensemble$', 
            r'\s+Quartet$', r'\s+Trio$', r'\s+Group$'
        ]
        for pattern in common_suffixes:
            artist_name = re.sub(pattern, '', artist_name, flags=re.IGNORECASE)
        
        return artist_name.strip()
    
    def normalize_isrc(self, isrc: str) -> str:
        """Normalize an ISRC code.
        
        Args:
            isrc: ISRC code to normalize
        
        Returns:
            Normalized ISRC code
        """
        if not isrc:
            return ""
            
        # Convert to string if not already and remove whitespace
        isrc = str(isrc).strip()
        
        # Remove common separators (hyphens, spaces, dots)
        isrc = re.sub(r'[\s\-\.]', '', isrc)
        
        # ISRC should be 12 characters
        # Format: CC-XXX-YY-NNNNN (Country-Registrant-Year-Number)
        # Return uppercase ISRC
        return isrc.upper()
    
    def get_canonical_title(self, title: str) -> str:
        """Get canonical version of the title without version/remix info.
        
        Args:
            title: Track title
        
        Returns:
            Canonical title with version/remix information removed
        """
        canonical = title
        
        # Remove various versions, remixes, etc.
        for patterns in self.patterns.values():
            for pattern in patterns:
                canonical = re.sub(pattern, '', canonical, flags=re.IGNORECASE)
        
        # Remove anything in parentheses or brackets
        canonical = re.sub(r'\([^)]*\)', '', canonical)
        canonical = re.sub(r'\[[^]]*\]', '', canonical)
        
        # Clean up multiple spaces
        canonical = re.sub(r'\s+', ' ', canonical)
        
        return canonical.strip()
    
    def get_primary_artist(self, artist_name: str) -> str:
        """Extract the primary artist from a compound artist name.
        
        Args:
            artist_name: Artist name, potentially with features
        
        Returns:
            Primary artist name
        """
        # Remove anything in parentheses (often contains features)
        artist = re.sub(r'\([^)]*\)', '', artist_name)
        
        # Handle explicit "feat." type separators
        for pattern in self.patterns['featuring']:
            artist = re.split(pattern, artist, maxsplit=1, flags=re.IGNORECASE)[0]
        
        # Split on first occurrence of a separator
        for separator in self.artist_separators:
            if separator.lower() in artist.lower():
                artist = artist.lower().split(separator.lower(), 1)[0]
                break
        
        return self.normalize_text(artist)
