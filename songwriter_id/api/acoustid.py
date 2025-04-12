"""AcoustID API integration for audio fingerprinting."""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import acoustid
import chromaprint

logger = logging.getLogger(__name__)


class AcoustIDClient:
    """Client for interacting with the AcoustID API."""

    def __init__(self, api_key: str):
        """Initialize the AcoustID client.

        Args:
            api_key: AcoustID API key
        """
        self.api_key = api_key

    def generate_fingerprint(self, audio_file: str) -> Tuple[float, str]:
        """Generate acoustic fingerprint from audio file.

        Args:
            audio_file: Path to the audio file

        Returns:
            Tuple of (duration, fingerprint)
        """
        try:
            duration, fp_encoded = acoustid.fingerprint_file(audio_file)
            fingerprint = chromaprint.decode_fingerprint(fp_encoded)[0]
            return duration, fingerprint
        except Exception as e:
            logger.error(f"Error generating fingerprint: {e}")
            raise

    def lookup_recording(self, duration: float, fingerprint: str) -> List[Dict]:
        """Look up recording by fingerprint.

        Args:
            duration: Audio duration in seconds
            fingerprint: Chromaprint fingerprint

        Returns:
            List of matching recordings with metadata
        """
        try:
            results = acoustid.lookup(self.api_key, fingerprint, duration, meta="recordings")
            return results.get("results", [])
        except Exception as e:
            logger.error(f"AcoustID lookup error: {e}")
            return []

    def identify_track(self, audio_file: str) -> List[Dict]:
        """Identify track using audio fingerprinting.

        Args:
            audio_file: Path to the audio file

        Returns:
            List of potential matches with metadata
        """
        try:
            # Generate fingerprint
            duration, fingerprint = self.generate_fingerprint(audio_file)
            
            # Lookup recording
            matches = self.lookup_recording(duration, fingerprint)
            
            results = []
            for match in matches:
                if "recordings" in match:
                    for recording in match["recordings"]:
                        result = {
                            "id": recording.get("id"),
                            "title": recording.get("title"),
                            "score": match.get("score", 0)
                        }
                        
                        if "artists" in recording:
                            result["artists"] = [a.get("name") for a in recording["artists"]]
                            
                        results.append(result)
            
            return results
        except Exception as e:
            logger.error(f"Track identification error: {e}")
            return []
