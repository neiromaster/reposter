from unittest.mock import AsyncMock

import pytest

from src.reposter.models import Post as VkPost
from src.reposter.processing.post_processor import PostProcessor
from src.reposter.processing.steps import ProcessingStep


@pytest.mark.asyncio
async def test_post_processor():
    """Test that PostProcessor calls all steps."""
    # Arrange
    mock_step1 = AsyncMock(spec=ProcessingStep)
    mock_step2 = AsyncMock(spec=ProcessingStep)
    steps = [mock_step1, mock_step2]
    post_processor = PostProcessor(steps)
    vk_post = VkPost(id=1, owner_id=1, from_id=1, date=1, text="test", attachments=[], is_pinned=0)

    # Act
    await post_processor.process_post(vk_post)

    # Assert
    mock_step1.process.assert_awaited_once()
    mock_step2.process.assert_awaited_once()
