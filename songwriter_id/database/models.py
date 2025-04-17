"""Database models for the songwriter identification system."""

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()


class Track(Base):
    """Represents a music track in the catalog."""

    __tablename__ = "tracks"

    track_id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False, index=True)
    artist_name = Column(String(255), nullable=False, index=True)
    track_isrc = Column(String(32), nullable=True, index=True, unique=True)
    release_title = Column(String(255), nullable=True)
    duration = Column(String, nullable=True)
    audio_path = Column(String(512), nullable=True)
    identification_status = Column(String(50), default="pending")
    confidence_score = Column(Float, default=0.0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    songwriter_credits = relationship(
        "SongwriterCredit", back_populates="track")
    identification_attempts = relationship(
        "IdentificationAttempt", back_populates="track")

    def __repr__(self):
        return f"<Track {self.track_id}: {self.title} by {self.artist_name}>"


class SongwriterCredit(Base):
    """Represents a songwriter credit for a track."""

    __tablename__ = "songwriter_credits"

    credit_id = Column(Integer, primary_key=True)
    track_id = Column(Integer, ForeignKey("tracks.track_id"), nullable=False)
    songwriter_name = Column(String(255), nullable=False, index=True)
    role = Column(String(50), nullable=True)  # composer, lyricist, etc.
    share_percentage = Column(Float, nullable=True)
    publisher_name = Column(String(255), nullable=True)
    source_of_info = Column(String(100), nullable=True)
    confidence_score = Column(Float, default=0.0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    track = relationship("Track", back_populates="songwriter_credits")

    def __repr__(self):
        return f"<SongwriterCredit {self.credit_id}: {self.songwriter_name} ({self.role}) for track {self.track_id}>"


class IdentificationAttempt(Base):
    """Represents an attempt to identify songwriter credits for a track."""

    __tablename__ = "identification_attempts"

    attempt_id = Column(Integer, primary_key=True)
    track_id = Column(Integer, ForeignKey("tracks.track_id"), nullable=False)
    source_used = Column(String(100), nullable=False)
    query_performed = Column(Text, nullable=True)
    result = Column(Text, nullable=True)
    confidence_score = Column(Float, default=0.0)
    timestamp = Column(DateTime, server_default=func.now())

    track = relationship("Track", back_populates="identification_attempts")

    def __repr__(self):
        return f"<IdentificationAttempt {self.attempt_id}: {self.source_used} for track {self.track_id}>"
