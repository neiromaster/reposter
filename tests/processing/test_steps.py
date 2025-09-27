# type: ignore[reportPrivateUsage]
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.reposter.exceptions import PostProcessingError
from src.reposter.managers.vk_manager import VKManager
from src.reposter.managers.ytdlp_manager import YTDLPManager
from src.reposter.models.dto import (
    Attachment,
    Photo,
    PhotoSize,
    TelegramPost,
    Video,
)
from src.reposter.models.dto import (
    Post as VkPost,
)
from src.reposter.processing.steps import (
    AttachmentDownloaderStep,
    LinkNormalizationStep,
    TagExtractionStep,
)


@pytest.fixture
def mock_vk_manager() -> AsyncMock:
    """Fixture for mocking the VK manager."""
    return AsyncMock(spec=VKManager)


@pytest.fixture
def mock_ytdlp_manager() -> AsyncMock:
    """Fixture for mocking the YTDLP manager."""
    return AsyncMock(spec=YTDLPManager)


@pytest.mark.asyncio
async def test_link_normalization_step():
    """Test LinkNormalizationStep."""
    # Arrange
    step = LinkNormalizationStep()
    vk_post = VkPost(id=1, owner_id=1, from_id=1, date=1, text="[club123|My Club]", attachments=[], is_pinned=0)
    prepared_post = TelegramPost(text=vk_post.text, attachments=[])

    # Act
    await step.process(vk_post, prepared_post)

    # Assert
    assert prepared_post.text == "[My Club](vk.com/club123)"


@pytest.mark.asyncio
async def test_tag_extraction_step():
    """Test TagExtractionStep."""
    # Arrange
    step = TagExtractionStep()
    vk_post = VkPost(id=1, owner_id=1, from_id=1, date=1, text="Hello\n#tag1 #tag2", attachments=[], is_pinned=0)
    prepared_post = TelegramPost(text=vk_post.text, attachments=[])

    # Act
    await step.process(vk_post, prepared_post)

    # Assert
    assert prepared_post.text == "Hello"
    assert prepared_post.tags == ["tag1", "tag2"]


@pytest.mark.asyncio
async def test_attachment_downloader_step_photo(mock_vk_manager: AsyncMock, mock_ytdlp_manager: AsyncMock):
    """Test AttachmentDownloaderStep with a photo."""
    # Arrange
    step = AttachmentDownloaderStep(mock_vk_manager, mock_ytdlp_manager)
    mock_vk_manager.download_file.return_value = Path("photo.jpg")
    vk_post = VkPost(
        id=1,
        owner_id=1,
        from_id=1,
        date=1,
        text="",
        attachments=[
            Attachment(
                type="photo",
                photo=Photo(
                    id=1,
                    owner_id=1,
                    sizes=[
                        PhotoSize(
                            type="x",
                            url="http://example.com/photo.jpg",
                            width=1,
                            height=1,
                        )
                    ],
                    orig_photo=PhotoSize(
                        type="x",
                        url="http://example.com/photo.jpg",
                        width=1,
                        height=1,
                    ),
                ),
            )
        ],
        is_pinned=0,
    )
    prepared_post = TelegramPost(text=vk_post.text, attachments=[])

    # Act
    await step.process(vk_post, prepared_post)

    # Assert
    assert len(prepared_post.attachments) == 1
    assert prepared_post.attachments[0].filename == "photo.jpg"


@pytest.mark.asyncio
async def test_attachment_downloader_step_video(mock_vk_manager: AsyncMock, mock_ytdlp_manager: AsyncMock):
    """Test AttachmentDownloaderStep with a video."""
    # Arrange
    step = AttachmentDownloaderStep(mock_vk_manager, mock_ytdlp_manager)
    mock_ytdlp_manager.download_video.return_value = Path("video.mp4")
    mock_vk_manager.download_file.return_value = Path("thumbnail.jpg")

    with patch("pymediainfo.MediaInfo.parse") as mock_media_info:
        mock_media_info.return_value.tracks = [MagicMock(track_type="Video", width=1920, height=1080)]

        vk_post = VkPost(
            id=1,
            owner_id=1,
            from_id=1,
            date=1,
            text="",
            attachments=[
                Attachment(
                    type="video",
                    video=Video(
                        id=1,
                        owner_id=1,
                        title="video_title",
                        access_key="",
                        image=[],
                    ),
                )
            ],
            is_pinned=0,
        )
        prepared_post = TelegramPost(text=vk_post.text, attachments=[])

        # Act
        await step.process(vk_post, prepared_post)

        # Assert
        assert len(prepared_post.attachments) == 1
        assert prepared_post.attachments[0].filename == "video_title.mp4"


@pytest.mark.asyncio
async def test_process_video_download_fails(mock_vk_manager: AsyncMock, mock_ytdlp_manager: AsyncMock):
    """Test _process_video when video download fails."""
    # Arrange
    step = AttachmentDownloaderStep(mock_vk_manager, mock_ytdlp_manager)
    mock_ytdlp_manager.download_video.return_value = None
    video = MagicMock()

    # Act & Assert
    with pytest.raises(PostProcessingError, match="Не удалось скачать видео"):
        await step._process_video(video)


@pytest.mark.asyncio
async def test_process_video_thumbnail_download_fails(mock_vk_manager: AsyncMock, mock_ytdlp_manager: AsyncMock):
    """Test _process_video when thumbnail download fails."""
    # Arrange
    step = AttachmentDownloaderStep(mock_vk_manager, mock_ytdlp_manager)
    mock_ytdlp_manager.download_video.return_value = Path("video.mp4")
    mock_vk_manager.download_file.return_value = None
    video = MagicMock(image=[MagicMock(width=1, height=1)], title="video_title")

    with patch("pymediainfo.MediaInfo.parse") as mock_media_info:
        mock_media_info.return_value.tracks = [MagicMock(track_type="Video", width=1920, height=1080)]

        # Act
        processed_video = await step._process_video(video)

        # Assert
        assert processed_video.thumbnail_path is None


@pytest.mark.asyncio
async def test_process_video_media_info_fails(mock_vk_manager: AsyncMock, mock_ytdlp_manager: AsyncMock):
    """Test _process_video when MediaInfo.parse fails."""
    # Arrange
    step = AttachmentDownloaderStep(mock_vk_manager, mock_ytdlp_manager)
    mock_ytdlp_manager.download_video.return_value = Path("video.mp4")
    mock_vk_manager.download_file.return_value = Path("thumbnail.jpg")
    video = MagicMock(image=[MagicMock(width=1, height=1)], title="video_title")

    with (
        patch("pymediainfo.MediaInfo.parse", side_effect=Exception("Test exception")),
        pytest.raises(PostProcessingError, match="Не удалось получить метаданные видео"),
    ):
        # Act
        await step._process_video(video)


@pytest.mark.asyncio
async def test_process_photo_download_fails(mock_vk_manager: AsyncMock, mock_ytdlp_manager: AsyncMock):
    """Test _process_photo when photo download fails."""
    # Arrange
    step = AttachmentDownloaderStep(mock_vk_manager, mock_ytdlp_manager)
    mock_vk_manager.download_file.return_value = None
    photo = MagicMock()

    # Act & Assert
    with pytest.raises(PostProcessingError, match="Не удалось скачать фото"):
        await step._process_photo(photo)


@pytest.mark.asyncio
async def test_process_audio_download_fails(mock_vk_manager: AsyncMock, mock_ytdlp_manager: AsyncMock):
    """Test _process_audio when audio download fails."""
    # Arrange
    step = AttachmentDownloaderStep(mock_vk_manager, mock_ytdlp_manager)
    mock_vk_manager.download_file.return_value = None
    audio = MagicMock()

    # Act & Assert
    with pytest.raises(PostProcessingError, match="Не удалось скачать аудио"):
        await step._process_audio(audio)


@pytest.mark.asyncio
async def test_process_doc_download_fails(mock_vk_manager: AsyncMock, mock_ytdlp_manager: AsyncMock):
    """Test _process_doc when doc download fails."""
    # Arrange
    step = AttachmentDownloaderStep(mock_vk_manager, mock_ytdlp_manager)
    mock_vk_manager.download_file.return_value = None
    doc = MagicMock()

    # Act & Assert
    with pytest.raises(PostProcessingError, match="Не удалось скачать документ"):
        await step._process_doc(doc)
