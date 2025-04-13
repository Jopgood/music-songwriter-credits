"""API integration package for the songwriter identification system."""

from songwriter_id.api.musicbrainz import MusicBrainzClient

# Import AcoustIDClient only if the chromaprint library is available
try:
    from songwriter_id.api.acoustid import AcoustIDClient
    __all__ = ['MusicBrainzClient', 'AcoustIDClient']
except ImportError:
    __all__ = ['MusicBrainzClient']
