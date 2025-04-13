"""API integration package for the songwriter identification system."""

from songwriter_id.api.musicbrainz import MusicBrainzClient
from songwriter_id.api.acoustid import AcoustIDClient

__all__ = ['MusicBrainzClient', 'AcoustIDClient']
