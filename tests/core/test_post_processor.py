# type: ignore[reportPrivateUsage]
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.reposter.core.post_processor import PostProcessor
from src.reposter.managers.vk_manager import VKManager
from src.reposter.managers.ytdlp_manager import YTDLPManager
from src.reposter.models.dto import (
    Attachment,
    Audio,
    Doc,
    Photo,
    PhotoSize,
    Video,
)
from src.reposter.models.dto import (
    Post as VkPost,
)


@pytest.fixture
def mock_vk_manager() -> AsyncMock:
    """Fixture for mocking the VK manager."""
    return AsyncMock(spec=VKManager)


@pytest.fixture
def mock_ytdlp_manager() -> AsyncMock:
    """Fixture for mocking the YTDLP manager."""
    return AsyncMock(spec=YTDLPManager)


@pytest.fixture
def post_processor(mock_vk_manager: VKManager, mock_ytdlp_manager: YTDLPManager) -> PostProcessor:
    """Fixture for creating a PostProcessor instance."""
    return PostProcessor(mock_vk_manager, mock_ytdlp_manager)


@pytest.mark.asyncio
async def test_process_post_no_attachments(post_processor: PostProcessor):
    """Test processing a post with no attachments."""
    # Arrange
    vk_post = VkPost(
        id=1,
        owner_id=1,
        from_id=1,
        date=1,
        text="Hello, world!",
        attachments=[],
        is_pinned=0,
    )

    # Act
    processed_post = await post_processor.process_post(vk_post)

    # Assert
    assert processed_post.text == "Hello, world!"
    assert processed_post.attachments == []


@pytest.mark.asyncio
async def test_process_post_with_photo(post_processor: PostProcessor, mock_vk_manager: AsyncMock):
    """Test processing a post with a photo attachment."""
    # Arrange
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

    # Act
    processed_post = await post_processor.process_post(vk_post)

    # Assert
    assert len(processed_post.attachments) == 1
    assert processed_post.attachments[0].filename == "photo.jpg"


@pytest.mark.asyncio
async def test_process_post_with_video(
    post_processor: PostProcessor, mock_ytdlp_manager: AsyncMock, mock_vk_manager: AsyncMock
):
    """Test processing a post with a video attachment."""
    # Arrange
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

        # Act
        processed_post = await post_processor.process_post(vk_post)

        # Assert
        assert len(processed_post.attachments) == 1
        assert processed_post.attachments[0].filename == "video_title.mp4"


@pytest.mark.asyncio
async def test_process_post_with_audio(post_processor: PostProcessor, mock_vk_manager: AsyncMock):
    """Test processing a post with an audio attachment."""
    # Arrange
    mock_vk_manager.download_file.return_value = Path("audio.mp3")
    vk_post = VkPost(
        id=1,
        owner_id=1,
        from_id=1,
        date=1,
        text="",
        attachments=[
            Attachment(
                type="audio",
                audio=Audio(
                    id=1,
                    owner_id=1,
                    artist="artist",
                    title="title",
                    url="http://example.com/audio.mp3",
                ),
            )
        ],
        is_pinned=0,
    )

    # Act
    processed_post = await post_processor.process_post(vk_post)

    # Assert
    assert len(processed_post.attachments) == 1
    assert processed_post.attachments[0].filename == "artist - title.mp3"


@pytest.mark.asyncio
async def test_process_post_with_doc(post_processor: PostProcessor, mock_vk_manager: AsyncMock):
    """Test processing a post with a document attachment."""
    # Arrange
    mock_vk_manager.download_file.return_value = Path("doc.txt")
    vk_post = VkPost(
        id=1,
        owner_id=1,
        from_id=1,
        date=1,
        text="",
        attachments=[
            Attachment(
                type="doc",
                doc=Doc(
                    id=1,
                    owner_id=1,
                    title="doc_title",
                    url="http://example.com/doc.txt",
                ),
            )
        ],
        is_pinned=0,
    )

    # Act
    processed_post = await post_processor.process_post(vk_post)

    # Assert
    assert len(processed_post.attachments) == 1
    assert processed_post.attachments[0].filename == "doc_title.txt"


@pytest.mark.asyncio
async def test_process_video_download_fails(post_processor: PostProcessor, mock_ytdlp_manager: AsyncMock):
    """Test _process_video when video download fails."""
    # Arrange
    mock_ytdlp_manager.download_video.return_value = None
    video = MagicMock()

    # Act & Assert
    with pytest.raises(Exception, match="Не удалось скачать видео"):
        await post_processor._process_video(video)


@pytest.mark.asyncio
async def test_process_video_thumbnail_download_fails(
    post_processor: PostProcessor, mock_ytdlp_manager: AsyncMock, mock_vk_manager: AsyncMock
):
    """Test _process_video when thumbnail download fails."""
    # Arrange
    mock_ytdlp_manager.download_video.return_value = Path("video.mp4")
    mock_vk_manager.download_file.return_value = None
    video = MagicMock(image=[MagicMock(width=1, height=1)], title="video_title")

    with patch("pymediainfo.MediaInfo.parse") as mock_media_info:
        mock_media_info.return_value.tracks = [MagicMock(track_type="Video", width=1920, height=1080)]

        # Act
        processed_video = await post_processor._process_video(video)

        # Assert
        assert processed_video.thumbnail_path is None


@pytest.mark.asyncio
async def test_process_video_media_info_fails(
    post_processor: PostProcessor, mock_ytdlp_manager: AsyncMock, mock_vk_manager: AsyncMock
):
    """Test _process_video when MediaInfo.parse fails."""
    # Arrange
    mock_ytdlp_manager.download_video.return_value = Path("video.mp4")
    mock_vk_manager.download_file.return_value = Path("thumbnail.jpg")
    video = MagicMock(image=[MagicMock(width=1, height=1)], title="video_title")

    with (
        patch("pymediainfo.MediaInfo.parse", side_effect=Exception("Test exception")),
        pytest.raises(Exception, match="Не удалось получить метаданные видео"),
    ):
        # Act
        await post_processor._process_video(video)


@pytest.mark.asyncio
async def test_process_photo_download_fails(post_processor: PostProcessor, mock_vk_manager: AsyncMock):
    """Test _process_photo when photo download fails."""
    # Arrange
    mock_vk_manager.download_file.return_value = None
    photo = MagicMock()

    # Act & Assert
    with pytest.raises(Exception, match="Не удалось скачать фото"):
        await post_processor._process_photo(photo)


@pytest.mark.asyncio
async def test_process_audio_download_fails(post_processor: PostProcessor, mock_vk_manager: AsyncMock):
    """Test _process_audio when audio download fails."""
    # Arrange
    mock_vk_manager.download_file.return_value = None
    audio = MagicMock()

    # Act & Assert
    with pytest.raises(Exception, match="Не удалось скачать аудио"):
        await post_processor._process_audio(audio)


@pytest.mark.asyncio
async def test_process_doc_download_fails(post_processor: PostProcessor, mock_vk_manager: AsyncMock):
    """Test _process_doc when doc download fails."""
    # Arrange
    mock_vk_manager.download_file.return_value = None
    doc = MagicMock()

    # Act & Assert
    with pytest.raises(Exception, match="Не удалось скачать документ"):
        await post_processor._process_doc(doc)
