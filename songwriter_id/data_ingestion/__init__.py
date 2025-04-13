"""Data ingestion module for parsing and importing music catalogs."""

from songwriter_id.data_ingestion.parser import CatalogParser
from songwriter_id.data_ingestion.normalizer import TrackNormalizer
from songwriter_id.data_ingestion.importer import CatalogImporter

__all__ = ['CatalogParser', 'TrackNormalizer', 'CatalogImporter']
