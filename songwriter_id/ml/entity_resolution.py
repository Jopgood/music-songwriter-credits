"""Entity resolution model for matching similar artist and title strings."""

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
from fuzzywuzzy import fuzz
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


class TextSimilarityFeatures(BaseEstimator, TransformerMixin):
    """Extract text similarity features for entity resolution."""

    def fit(self, X, y=None):
        """Fit the transformer."""
        return self

    def transform(self, X):
        """Transform the input data to similarity features.

        Args:
            X: List of (string1, string2) tuples

        Returns:
            Array of similarity features
        """
        features = []
        for str1, str2 in X:
            features.append([
                fuzz.ratio(str1, str2) / 100,
                fuzz.partial_ratio(str1, str2) / 100,
                fuzz.token_sort_ratio(str1, str2) / 100,
                fuzz.token_set_ratio(str1, str2) / 100,
                # Basic character-level similarity
                len(str1) / (len(str2) + 1),
                len(set(str1.lower()) & set(str2.lower())) / len(set(str1.lower()) | set(str2.lower())) if len(set(str1.lower()) | set(str2.lower())) > 0 else 0,
            ])
        return np.array(features)


class EntityResolutionModel:
    """Model for entity resolution of artist names and track titles."""

    def __init__(self):
        """Initialize the entity resolution model."""
        self.model = Pipeline([
            ('features', TextSimilarityFeatures()),
            ('scaler', StandardScaler()),
            ('classifier', RandomForestClassifier(n_estimators=100, random_state=42))
        ])
        self.is_trained = False

    def train(self, positive_pairs: List[Tuple[str, str]], negative_pairs: List[Tuple[str, str]]):
        """Train the entity resolution model.

        Args:
            positive_pairs: List of matching string pairs
            negative_pairs: List of non-matching string pairs
        """
        X = positive_pairs + negative_pairs
        y = [1] * len(positive_pairs) + [0] * len(negative_pairs)
        
        self.model.fit(X, y)
        self.is_trained = True
        logger.info(f"Trained entity resolution model with {len(positive_pairs)} positive and {len(negative_pairs)} negative examples")

    def predict(self, pairs: List[Tuple[str, str]]) -> List[float]:
        """Predict match probability for string pairs.

        Args:
            pairs: List of (string1, string2) tuples

        Returns:
            List of match probabilities
        """
        if not self.is_trained:
            logger.warning("Model is not trained yet")
            return [0.5] * len(pairs)
            
        return self.model.predict_proba(pairs)[:, 1]

    def find_best_match(self, query: str, candidates: List[str]) -> Tuple[str, float]:
        """Find the best matching candidate for a query string.

        Args:
            query: Query string
            candidates: List of candidate strings

        Returns:
            Tuple of (best_match, confidence)
        """
        if not candidates:
            return None, 0.0
            
        pairs = [(query, candidate) for candidate in candidates]
        probabilities = self.predict(pairs)
        
        best_idx = np.argmax(probabilities)
        return candidates[best_idx], probabilities[best_idx]

    def save_model(self, filepath: str):
        """Save the model to a file.

        Args:
            filepath: Path to save the model
        """
        import joblib
        joblib.dump(self.model, filepath)
        logger.info(f"Saved entity resolution model to {filepath}")

    @classmethod
    def load_model(cls, filepath: str) -> 'EntityResolutionModel':
        """Load a model from a file.

        Args:
            filepath: Path to the model file

        Returns:
            Loaded model
        """
        import joblib
        instance = cls()
        instance.model = joblib.load(filepath)
        instance.is_trained = True
        logger.info(f"Loaded entity resolution model from {filepath}")
        return instance
