"""Audio fingerprinting utilities for songwriter identification."""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import librosa
import numpy as np

logger = logging.getLogger(__name__)


class AudioProcessor:
    """Audio processing utilities for feature extraction and fingerprinting."""

    def __init__(self, sample_rate: int = 22050):
        """Initialize the audio processor.

        Args:
            sample_rate: Target sample rate for audio processing
        """
        self.sample_rate = sample_rate

    def load_audio(self, file_path: str) -> Tuple[np.ndarray, int]:
        """Load audio file and convert to mono if needed.

        Args:
            file_path: Path to the audio file

        Returns:
            Tuple of (audio_data, sample_rate)
        """
        try:
            y, sr = librosa.load(file_path, sr=self.sample_rate, mono=True)
            return y, sr
        except Exception as e:
            logger.error(f"Error loading audio file {file_path}: {e}")
            raise

    def extract_features(self, audio_data: np.ndarray, sample_rate: int) -> Dict:
        """Extract audio features from loaded audio data.

        Args:
            audio_data: Audio time series
            sample_rate: Sample rate of the audio

        Returns:
            Dictionary of extracted features
        """
        features = {}
        
        # Basic features
        features['duration'] = librosa.get_duration(y=audio_data, sr=sample_rate)
        
        # Spectral features
        features['spectral_centroid'] = np.mean(librosa.feature.spectral_centroid(y=audio_data, sr=sample_rate)[0])
        features['spectral_bandwidth'] = np.mean(librosa.feature.spectral_bandwidth(y=audio_data, sr=sample_rate)[0])
        features['spectral_rolloff'] = np.mean(librosa.feature.spectral_rolloff(y=audio_data, sr=sample_rate)[0])
        
        # Rhythm features
        tempo, _ = librosa.beat.beat_track(y=audio_data, sr=sample_rate)
        features['tempo'] = tempo
        
        # MFCCs (first 13 coefficients)
        mfccs = librosa.feature.mfcc(y=audio_data, sr=sample_rate, n_mfcc=13)
        for i, mfcc in enumerate(mfccs):
            features[f'mfcc_{i+1}'] = np.mean(mfcc)
        
        return features

    def compute_fingerprint(self, audio_data: np.ndarray, sample_rate: int) -> np.ndarray:
        """Compute a simple fingerprint based on chroma features.

        Args:
            audio_data: Audio time series
            sample_rate: Sample rate of the audio

        Returns:
            Audio fingerprint array
        """
        # Extract chroma features
        chroma = librosa.feature.chroma_cqt(y=audio_data, sr=sample_rate)
        
        # Downsample to create a compact fingerprint
        # We'll take the mean of small windows to create a more robust fingerprint
        window_size = 50
        if chroma.shape[1] >= window_size:
            num_windows = chroma.shape[1] // window_size
            fingerprint = np.zeros((chroma.shape[0], num_windows))
            
            for i in range(num_windows):
                window = chroma[:, i*window_size:(i+1)*window_size]
                fingerprint[:, i] = np.mean(window, axis=1)
        else:
            # If the audio is too short, just use the mean of the entire chroma
            fingerprint = np.mean(chroma, axis=1).reshape(-1, 1)
        
        return fingerprint

    def compare_fingerprints(self, fp1: np.ndarray, fp2: np.ndarray) -> float:
        """Compare two fingerprints and return similarity score.

        Args:
            fp1: First fingerprint
            fp2: Second fingerprint

        Returns:
            Similarity score between 0 and 1
        """
        # If fingerprints are different sizes, use the smaller one as a template
        # and slide it across the larger one, taking the maximum similarity
        if fp1.shape[1] != fp2.shape[1]:
            if fp1.shape[1] > fp2.shape[1]:
                fp1, fp2 = fp2, fp1  # Make fp1 the smaller one
                
            max_similarity = 0.0
            for i in range(fp2.shape[1] - fp1.shape[1] + 1):
                window = fp2[:, i:i+fp1.shape[1]]
                # Compute cosine similarity
                similarity = np.sum(fp1 * window) / (np.sqrt(np.sum(fp1**2)) * np.sqrt(np.sum(window**2)))
                max_similarity = max(max_similarity, similarity)
            return max_similarity
        else:
            # Compute cosine similarity directly for same-sized fingerprints
            return np.sum(fp1 * fp2) / (np.sqrt(np.sum(fp1**2)) * np.sqrt(np.sum(fp2**2)))

    def process_file(self, file_path: str) -> Dict:
        """Process an audio file and extract features and fingerprint.

        Args:
            file_path: Path to the audio file

        Returns:
            Dictionary with audio features and fingerprint
        """
        try:
            # Load audio
            audio_data, sample_rate = self.load_audio(file_path)
            
            # Extract features
            features = self.extract_features(audio_data, sample_rate)
            
            # Compute fingerprint
            fingerprint = self.compute_fingerprint(audio_data, sample_rate)
            
            return {
                'features': features,
                'fingerprint': fingerprint,
                'duration': features['duration'],
                'sample_rate': sample_rate
            }
        except Exception as e:
            logger.error(f"Error processing audio file {file_path}: {e}")
            return {'error': str(e)}
