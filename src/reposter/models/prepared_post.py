from __future__ import annotations

from pydantic import BaseModel, Field

from .downloaded_artifact import DownloadedArtifact
from .prepared_attachment import (
    PreparedAudioAttachment,
    PreparedDocumentAttachment,
    PreparedPhotoAttachment,
    PreparedVideoAttachment,
)


class PreparedPost(BaseModel):
    """A post that is fully prepared for sending."""

    text: str
    attachments: list[
        PreparedPhotoAttachment | PreparedVideoAttachment | PreparedAudioAttachment | PreparedDocumentAttachment
    ]
    tags: list[str] = Field(default_factory=list)
    downloaded_artifacts: list[DownloadedArtifact] = Field(default_factory=list[DownloadedArtifact], exclude=True)
