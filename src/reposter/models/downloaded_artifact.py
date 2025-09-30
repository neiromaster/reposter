from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from .vk import Audio, Doc, Photo, Video


class BaseDownloadedArtifact(BaseModel):
    file_path: Path


class DownloadedPhotoArtifact(BaseDownloadedArtifact):
    type: Literal["photo"] = "photo"
    original_attachment: Photo


class DownloadedVideoArtifact(BaseDownloadedArtifact):
    type: Literal["video"] = "video"
    original_attachment: Video
    width: int
    height: int
    thumbnail_path: Path | None = None


class DownloadedAudioArtifact(BaseDownloadedArtifact):
    type: Literal["audio"] = "audio"
    original_attachment: Audio
    artist: str
    title: str


class DownloadedDocumentArtifact(BaseDownloadedArtifact):
    type: Literal["doc"] = "doc"
    original_attachment: Doc
    filename: str


DownloadedArtifact = (
    DownloadedPhotoArtifact | DownloadedVideoArtifact | DownloadedAudioArtifact | DownloadedDocumentArtifact
)
