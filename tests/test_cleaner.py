from pathlib import Path
from unittest.mock import patch

import pytest

from src.reposter.models.dto import PreparedAttachment, PreparedVideoAttachment
from src.reposter.utils.cleaner import delete_files_async


class TestCleaner:
    @pytest.mark.asyncio
    async def test_delete_files_async_single_file_exists(self, tmp_path: Path):
        """Test deleting a single file that exists."""
        # Create a temporary file
        test_file = tmp_path / "test_file.txt"
        test_file.write_text("test content")

        # Create a PreparedAttachment
        attachment = PreparedAttachment(file_path=test_file, filename="test_file.txt")

        # Call the function
        await delete_files_async([attachment])

        # Verify the file was deleted
        assert not test_file.exists()

    @pytest.mark.asyncio
    async def test_delete_files_async_single_file_not_exists(self):
        """Test deleting a single file that does not exist."""
        # When a file doesn't exist, it should not try to delete it and not log anything
        fake_file = Path("non_existent_file.txt")
        attachment = PreparedAttachment(file_path=fake_file, filename="non_existent_file.txt")

        # Mock the log function to capture the call
        with patch("src.reposter.utils.cleaner.log") as mock_log:
            # Call the function
            await delete_files_async([attachment])

            # Since the file doesn't exist, no log message should be made
            mock_log.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_files_async_with_exception(self, tmp_path: Path):
        """Test deleting files when an exception occurs."""
        with patch("src.reposter.utils.cleaner.Path.unlink", side_effect=Exception("Permission denied")):
            test_file = tmp_path / "test_file.txt"
            test_file.write_text("test content")

            attachment = PreparedAttachment(file_path=test_file, filename="test_file.txt")

            # Call the function
            await delete_files_async([attachment])

            # The file should still exist since the deletion failed
            assert test_file.exists()

    @pytest.mark.asyncio
    async def test_delete_files_async_multiple_files(self, tmp_path: Path):
        """Test deleting multiple files."""
        # Create temporary files
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("content 1")
        file2.write_text("content 2")

        # Create PreparedAttachments
        attachment1 = PreparedAttachment(file_path=file1, filename="file1.txt")
        attachment2 = PreparedAttachment(file_path=file2, filename="file2.txt")

        # Call the function
        await delete_files_async([attachment1, attachment2])

        # Verify both files were deleted
        assert not file1.exists()
        assert not file2.exists()

    @pytest.mark.asyncio
    async def test_delete_video_attachments_with_thumbnails(self, tmp_path: Path):
        """Test deleting video attachments with thumbnails."""
        # Create temporary files
        video_file = tmp_path / "video.mp4"
        thumbnail_file = tmp_path / "thumbnail.jpg"
        video_file.write_text("video content")
        thumbnail_file.write_text("thumbnail content")

        # Create a PreparedVideoAttachment with thumbnail
        attachment = PreparedVideoAttachment(
            file_path=video_file, filename="video.mp4", width=1920, height=1080, thumbnail_path=thumbnail_file
        )

        # Call the function
        await delete_files_async([attachment])

        # Verify both files were deleted
        assert not video_file.exists()
        assert not thumbnail_file.exists()

    @pytest.mark.asyncio
    async def test_delete_video_attachments_without_thumbnails(self, tmp_path: Path):
        """Test deleting video attachments without thumbnails."""
        # Create temporary video file
        video_file = tmp_path / "video.mp4"
        video_file.write_text("video content")

        # Create a PreparedVideoAttachment without thumbnail
        attachment = PreparedVideoAttachment(
            file_path=video_file, filename="video.mp4", width=1920, height=1080, thumbnail_path=None
        )

        # Call the function
        await delete_files_async([attachment])

        # Verify the video file was deleted
        assert not video_file.exists()
