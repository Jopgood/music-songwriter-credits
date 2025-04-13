"""API integration package for the songwriter identification system."""

from songwriter_id.api.musicbrainz import MusicBrainzClient

# Import MusicBrainzDatabaseClient
try:
    from songwriter_id.api.musicbrainz_db import MusicBrainzDatabaseClient
    __all__ = ['MusicBrainzClient', 'MusicBrainzDatabaseClient']
except ImportError as e:
    # SQLAlchemy may not be available or properly configured
    import logging
    logging.warning(f"MusicBrainzDatabaseClient not available: {e}")
    __all__ = ['MusicBrainzClient']

# Import AcoustIDClient only if the chromaprint library is available
try:
    from songwriter_id.api.acoustid import AcoustIDClient
    __all__ = ['MusicBrainzClient', 'MusicBrainzDatabaseClient', 'AcoustIDClient']
except ImportError:
    pass
