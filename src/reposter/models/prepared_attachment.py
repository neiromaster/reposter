from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class PreparedAttachment(BaseModel):
    """Base model for a processed attachment."""

    file_path: Path
    filename: str


class PreparedPhotoAttachment(PreparedAttachment):
    pass


class PreparedVideoAttachment(PreparedAttachment):
    width: int
    height: int
    thumbnail_path: Path | None = None


class PreparedAudioAttachment(PreparedAttachment):
    artist: str
    title: str


class PreparedDocumentAttachment(PreparedAttachment):
    pass
