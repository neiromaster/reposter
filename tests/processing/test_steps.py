# type: ignore[reportPrivateUsage]
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.reposter.managers.vk_manager import VKManager
from src.reposter.managers.ytdlp_manager import YTDLPManager
from src.reposter.models.dto import (
    Attachment,
    DownloadedArtifact,
    Photo,
    PhotoSize,
    PreparedPost,
)
from src.reposter.models.dto import (
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
    assert prepared_post.text == "[My Club](vk.com/club123)"


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
            DownloadedArtifact(
                type="photo",
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
