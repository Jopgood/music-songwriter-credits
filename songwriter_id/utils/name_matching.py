"""Utilities for name matching and normalization."""

import re
from difflib import SequenceMatcher
from typing import Dict, Tuple

# Cache for normalized names to avoid repeated normalization
normalized_name_cache = {}

def normalize_name(name: str) -> str:
    """Normalize a name for comparison.
    
    Args:
        name: Name to normalize
        
    Returns:
        Normalized name
    """
    # Check if already in cache
    if name in normalized_name_cache:
        return normalized_name_cache[name]
        
    # Convert to lowercase
    result = name.lower()
    
    # Remove punctuation that doesn't affect pronunciation
    result = re.sub(r'[\'",.:;!?()\[\]{}]', '', result)
    
    # Replace multiple spaces with single space
    result = re.sub(r'\s+', ' ', result)
    
    # Strip leading/trailing whitespace
    result = result.strip()
    
    # Store in cache
    normalized_name_cache[name] = result
    
    return result

def name_similarity(name1: str, name2: str) -> float:
    """Calculate similarity between two names.
    
    Args:
        name1: First name
        name2: Second name
        
    Returns:
        Similarity score between 0 and 1
    """
    # Normalize both names
    norm1 = normalize_name(name1)
    norm2 = normalize_name(name2)
    
    # Exact match after normalization
    if norm1 == norm2:
        return 1.0
        
    # Check if one is contained in the other
    if norm1 in norm2 or norm2 in norm1:
        return 0.9
        
    # Use SequenceMatcher for fuzzy string matching
    return SequenceMatcher(None, norm1, norm2).ratio()

def create_name_variations(name: str) -> Tuple[str, str, str]:
    """Create variations of a name for fuzzy matching.
    
    Args:
        name: Original name
        
    Returns:
        Tuple of (name_without_quotes, name_with_quotes, exact_name)
    """
    name_no_quotes = re.sub(r'[\'"]', '', name)
    name_with_quotes = f"'{name}'"  # For cases where quotes were added in DB
    
    return (name_no_quotes, name_with_quotes, name)
