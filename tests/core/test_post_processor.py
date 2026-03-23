# pyright: reportPrivateUsage=false
"""Tests for AttachmentDownloaderStep._download_video with thumbnail download failures."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import HttpUrl

from reposter.exceptions import PostProcessingError
from reposter.managers.vk_manager import VKManager
from reposter.managers.ytdlp_manager import YTDLPManager
from reposter.models import CoverSize as VkCoverSize
from reposter.models import Video as VkVideo
from reposter.processing.steps import AttachmentDownloaderStep


@pytest.mark.asyncio
async def test_download_video_continues_when_thumbnail_download_fails():
    """
    Test that video download continues successfully even when thumbnail download fails.

    Given:
        - A video with a thumbnail
        - ytdlp successfully downloads the video
        - vk.download_file raises an exception for the thumbnail

    When:
        - _download_video is called

    Then:
        - Video is downloaded successfully
        - thumbnail_path is None
        - No exception is raised
    """
    # Arrange
    mock_vk_manager = MagicMock(spec=VKManager)
    mock_ytdlp_manager = MagicMock(spec=YTDLPManager)

    # Mock video download success
    video_path = Path("/tmp/test_video.mp4")
    mock_ytdlp_manager.download_video = AsyncMock(return_value=video_path)

    # Mock thumbnail download failure
    mock_vk_manager.download_file = AsyncMock(side_effect=Exception("Network error"))

    # Create video with thumbnail
    video_with_thumb = VkVideo(
        id=123,
        owner_id=456,
        title="Test Video",
        description="Test description",
        image=[
            VkCoverSize(
                url=HttpUrl("https://example.com/thumb.jpg"),
                width=1280,
                height=720,
                with_padding=0,
            )
        ],
    )

    step = AttachmentDownloaderStep(vk_manager=mock_vk_manager, ytdlp_manager=mock_ytdlp_manager)

    # Mock MediaInfo.parse to return valid video metadata
    with patch("reposter.processing.steps.MediaInfo.parse") as mock_media_info:
        mock_track = MagicMock()
        mock_track.track_type = "Video"
        mock_track.width = 1920
        mock_track.height = 1080

        mock_media_info_return = MagicMock()
        mock_media_info_return.tracks = [mock_track]
        mock_media_info.return_value = mock_media_info_return

        # Act
        result = await step._download_video(video_with_thumb)

    # Assert
    assert result is not None
    assert result.file_path == video_path
    assert result.width == 1920
    assert result.height == 1080
    assert result.thumbnail_path is None  # Thumbnail should be None after failed download

    # Verify that download_file was called for thumbnail
    mock_vk_manager.download_file.assert_called_once()

    # Verify that video download was attempted
    mock_ytdlp_manager.download_video.assert_called_once_with(video_with_thumb.url)


@pytest.mark.asyncio
async def test_download_video_succeeds_without_thumbnail():
    """
    Test that video download succeeds when video has no thumbnail.

    Given:
        - A video without a thumbnail
        - ytdlp successfully downloads the video

    When:
        - _download_video is called

    Then:
        - Video is downloaded successfully
        - thumbnail_path is None
        - vk.download_file is never called
    """
    # Arrange
    mock_vk_manager = MagicMock(spec=VKManager)
    mock_ytdlp_manager = MagicMock(spec=YTDLPManager)

    # Mock video download success
    video_path = Path("/tmp/test_video.mp4")
    mock_ytdlp_manager.download_video = AsyncMock(return_value=video_path)

    # Create video without thumbnail
    video_without_thumb = VkVideo(
        id=123,
        owner_id=456,
        title="Test Video",
        description="Test description",
        image=[],  # No thumbnail
    )

    step = AttachmentDownloaderStep(vk_manager=mock_vk_manager, ytdlp_manager=mock_ytdlp_manager)

    # Mock MediaInfo.parse to return valid video metadata
    with patch("reposter.processing.steps.MediaInfo.parse") as mock_media_info:
        mock_track = MagicMock()
        mock_track.track_type = "Video"
        mock_track.width = 1920
        mock_track.height = 1080

        mock_media_info_return = MagicMock()
        mock_media_info_return.tracks = [mock_track]
        mock_media_info.return_value = mock_media_info_return

        # Act
        result = await step._download_video(video_without_thumb)

    # Assert
    assert result is not None
    assert result.file_path == video_path
    assert result.width == 1920
    assert result.height == 1080
    assert result.thumbnail_path is None

    # Verify that download_file was never called (no thumbnail)
    mock_vk_manager.download_file.assert_not_called()


@pytest.mark.asyncio
async def test_download_video_fails_when_video_download_fails():
    """
    Test that video download fails when ytdlp fails to download the video.

    Given:
        - A video
        - ytdlp fails to download the video (returns None)

    When:
        - _download_video is called

    Then:
        - PostProcessingError is raised
    """
    # Arrange
    mock_vk_manager = MagicMock(spec=VKManager)
    mock_ytdlp_manager = MagicMock(spec=YTDLPManager)

    # Mock video download failure
    mock_ytdlp_manager.download_video = AsyncMock(return_value=None)

    video = VkVideo(
        id=123,
        owner_id=456,
        title="Test Video",
        description="Test description",
        image=[],
    )

    step = AttachmentDownloaderStep(vk_manager=mock_vk_manager, ytdlp_manager=mock_ytdlp_manager)

    # Act & Assert
    with pytest.raises(PostProcessingError, match="Не удалось скачать видео"):
        await step._download_video(video)
