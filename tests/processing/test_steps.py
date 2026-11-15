# type: ignore[reportPrivateUsage]
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.reposter.managers.vk_manager import VKManager
from src.reposter.managers.ytdlp_manager import YTDLPManager
from src.reposter.models import (
    Attachment,
    Audio,
    Doc,
    DownloadedAudioArtifact,
    DownloadedDocumentArtifact,
    DownloadedPhotoArtifact,
    DownloadedVideoArtifact,
    Photo,
    PhotoSize,
    PreparedPost,
    Video,
)
from src.reposter.models import (
    Post as VkPost,
)
from src.reposter.processing.steps import (
    AttachmentDownloaderStep,
    AttachmentDtoCreationStep,
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
    prepared_post = PreparedPost(text=vk_post.text, attachments=[])

    # Act
    await step.process(vk_post, prepared_post)

    # Assert
    assert prepared_post.text == "[My Club](vk.ru/club123)"


@pytest.mark.asyncio
async def test_tag_extraction_step():
    """Test TagExtractionStep."""
    # Arrange
    step = TagExtractionStep()
    vk_post = VkPost(id=1, owner_id=1, from_id=1, date=1, text="Hello\n#tag1 #tag2", attachments=[], is_pinned=0)
    prepared_post = PreparedPost(text=vk_post.text, attachments=[])

    # Act
    await step.process(vk_post, prepared_post)

    # Assert
    assert prepared_post.text == "Hello\n#tag1 #tag2"
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
    prepared_post = PreparedPost(text=vk_post.text, attachments=[])

    # Act
    await step.process(vk_post, prepared_post)

    # Assert
    assert len(prepared_post.downloaded_artifacts) == 1
    assert prepared_post.downloaded_artifacts[0].type == "photo"


@pytest.mark.asyncio
async def test_attachment_dto_creation_step():
    """Test AttachmentDtoCreationStep."""
    # Arrange
    step = AttachmentDtoCreationStep()
    vk_post = VkPost(id=1, owner_id=1, from_id=1, date=1, text="", attachments=[], is_pinned=0)

    photo_attachment = Photo(
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
    )

    prepared_post = PreparedPost(
        text=vk_post.text,
        attachments=[],
        downloaded_artifacts=[
            DownloadedPhotoArtifact(
                original_attachment=photo_attachment,
                file_path=Path("photo.jpg"),
            ),
        ],
    )

    # Act
    await step.process(vk_post, prepared_post)

    # Assert
    assert len(prepared_post.attachments) == 1
    assert prepared_post.attachments[0].filename == "photo.jpg"


@pytest.mark.asyncio
async def test_attachment_dto_creation_step_video_title_with_slash():
    """A video title containing '/' must keep its full text: '/' becomes a space.

    An unsanitized title would later be truncated by Path(...).stem when the
    Boosty post title is derived from the filename.
    """
    # Arrange
    step = AttachmentDtoCreationStep()
    vk_post = VkPost(id=1, owner_id=1, from_id=1, date=1, text="", attachments=[], is_pinned=0)
    video = Video(id=1, owner_id=1, title="Готовим/тушим часть 2")
    artifact = DownloadedVideoArtifact(
        original_attachment=video,
        file_path=Path("video.mp4"),
        width=1920,
        height=1080,
    )
    prepared_post = PreparedPost(text=vk_post.text, attachments=[], downloaded_artifacts=[artifact])

    # Act
    await step.process(vk_post, prepared_post)

    # Assert
    assert len(prepared_post.attachments) == 1
    assert prepared_post.attachments[0].filename == "Готовим тушим часть 2.mp4"


@pytest.mark.asyncio
async def test_attachment_dto_creation_step_audio_name_with_slash():
    """An audio artist/title containing '/' must keep its full text in the filename."""
    # Arrange
    step = AttachmentDtoCreationStep()
    vk_post = VkPost(id=1, owner_id=1, from_id=1, date=1, text="", attachments=[], is_pinned=0)
    audio = Audio(id=1, owner_id=1, title="Highway/to Hell", artist="AC/DC", url="http://example.com/audio.mp3")
    artifact = DownloadedAudioArtifact(
        original_attachment=audio,
        file_path=Path("audio.mp3"),
        artist=audio.artist,
        title=audio.title,
    )
    prepared_post = PreparedPost(text=vk_post.text, attachments=[], downloaded_artifacts=[artifact])

    # Act
    await step.process(vk_post, prepared_post)

    # Assert
    assert len(prepared_post.attachments) == 1
    assert prepared_post.attachments[0].filename == "AC DC - Highway to Hell.mp3"


@pytest.mark.asyncio
async def test_attachment_dto_creation_step_doc_name_with_slash():
    """A doc title containing '/' must keep its full text in the filename."""
    # Arrange
    step = AttachmentDtoCreationStep()
    vk_post = VkPost(id=1, owner_id=1, from_id=1, date=1, text="", attachments=[], is_pinned=0)
    doc = Doc(id=1, owner_id=1, title="Отчёт/2024/итог", url="http://example.com/doc.pdf")
    artifact = DownloadedDocumentArtifact(
        original_attachment=doc,
        file_path=Path("doc.pdf"),
        filename=doc.title,
    )
    prepared_post = PreparedPost(text=vk_post.text, attachments=[], downloaded_artifacts=[artifact])

    # Act
    await step.process(vk_post, prepared_post)

    # Assert
    assert len(prepared_post.attachments) == 1
    assert prepared_post.attachments[0].filename == "Отчёт 2024 итог.pdf"
