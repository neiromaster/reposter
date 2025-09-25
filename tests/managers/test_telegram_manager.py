# type: ignore[reportPrivateUsage]
import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pyrogram.errors import ChannelPrivate, FloodWait
from pyrogram.types import (
    InputMediaAudio,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
)

from src.reposter.config.settings import AppConfig, Settings, TelegramConfig
from src.reposter.exceptions import TelegramManagerError
from src.reposter.managers.telegram_manager import TelegramManager
from src.reposter.models.dto import (
    PreparedAudioAttachment,
    PreparedDocumentAttachment,
    PreparedPhotoAttachment,
    PreparedVideoAttachment,
    TelegramPost,
)


@pytest.fixture
def settings() -> Settings:
    """Provides a mock Settings object for tests."""
    mock_settings = MagicMock(spec=Settings)
    mock_settings.app = AppConfig(session_name="test_session")
    mock_settings.telegram_api_id = 12345
    mock_settings.telegram_api_hash = "mock_hash"
    return mock_settings


@pytest.fixture
async def telegram_manager() -> AsyncGenerator[TelegramManager, None]:
    """Provides a TelegramManager instance for tests."""
    manager = TelegramManager()
    shutdown_event = asyncio.Event()
    manager.set_shutdown_event(shutdown_event)
    yield manager
    if manager._initialized:
        await manager.shutdown()


@pytest.mark.asyncio
@patch("src.reposter.managers.telegram_manager.Client")
async def test_setup_success(mock_client_class: MagicMock, telegram_manager: TelegramManager, settings: Settings):
    """Tests that the client is initialized and started on setup."""
    # Arrange
    mock_instance = AsyncMock()
    mock_client_class.return_value = mock_instance

    # Act
    await telegram_manager.setup(settings)

    # Assert
    mock_client_class.assert_called_once_with(
        "test_session",
        api_id=12345,
        api_hash="mock_hash",
    )
    mock_instance.start.assert_awaited_once()
    assert telegram_manager._initialized


@pytest.mark.asyncio
@patch("src.reposter.managers.telegram_manager.Client")
async def test_setup_exception(mock_client_class: MagicMock, telegram_manager: TelegramManager, settings: Settings):
    """Tests that setup fails gracefully if the client fails to start."""
    # Arrange
    mock_instance = AsyncMock()
    mock_instance.start.side_effect = Exception("Connection failed")
    mock_client_class.return_value = mock_instance

    # Act & Assert
    with pytest.raises(Exception, match="Connection failed"):
        await telegram_manager.setup(settings)

    assert not telegram_manager._initialized


@pytest.mark.asyncio
@patch("src.reposter.managers.telegram_manager.Client")
async def test_shutdown_success(mock_client_class: MagicMock, telegram_manager: TelegramManager, settings: Settings):
    """Tests that the client is stopped on shutdown."""
    # Arrange
    mock_instance = AsyncMock()
    mock_instance.is_connected = True
    mock_client_class.return_value = mock_instance

    await telegram_manager.setup(settings)
    assert telegram_manager._initialized

    # Act
    await telegram_manager.shutdown()

    # Assert
    mock_instance.stop.assert_awaited_once()
    assert not telegram_manager._initialized


@pytest.mark.asyncio
async def test_shutdown_not_initialized(telegram_manager: TelegramManager):
    """Tests that shutdown does nothing if the manager is not initialized."""
    # Act & Assert
    # This should not raise any exception
    await telegram_manager.shutdown()
    assert not telegram_manager._initialized


@pytest.mark.asyncio
@patch("src.reposter.managers.telegram_manager.Client")
async def test_update_config_restarts_on_change(
    mock_client_class: MagicMock, telegram_manager: TelegramManager, settings: Settings
):
    """Tests that the manager restarts if the configuration changes."""
    # Arrange
    mock_instance = AsyncMock()
    mock_client_class.return_value = mock_instance
    await telegram_manager.setup(settings)

    # Act
    new_settings = MagicMock(spec=Settings)
    new_settings.app = AppConfig(session_name="new_session")
    new_settings.telegram_api_id = 54321
    new_settings.telegram_api_hash = "new_hash"

    with (
        patch.object(telegram_manager, "shutdown", new_callable=AsyncMock) as mock_shutdown,
        patch.object(telegram_manager, "setup", new_callable=AsyncMock) as mock_setup,
    ):
        await telegram_manager.update_config(new_settings)

        # Assert
        mock_shutdown.assert_awaited_once()
        mock_setup.assert_awaited_once_with(new_settings)


@pytest.mark.asyncio
@patch("src.reposter.managers.telegram_manager.Client")
async def test_update_config_does_nothing_on_no_change(
    mock_client_class: MagicMock, telegram_manager: TelegramManager, settings: Settings
):
    """Tests that the manager does nothing if the configuration is the same."""
    # Arrange
    mock_instance = AsyncMock()
    mock_client_class.return_value = mock_instance
    await telegram_manager.setup(settings)

    # Act
    with (
        patch.object(telegram_manager, "shutdown", new_callable=AsyncMock) as mock_shutdown,
        patch.object(telegram_manager, "setup", new_callable=AsyncMock) as mock_setup,
    ):
        await telegram_manager.update_config(settings)

        # Assert
        mock_shutdown.assert_not_awaited()
        mock_setup.assert_not_awaited()


@pytest.mark.asyncio
@patch("src.reposter.managers.telegram_manager.Client")
async def test_post_to_channels_text_only(
    mock_client_class: MagicMock, telegram_manager: TelegramManager, settings: Settings
):
    """Tests posting a message with only text."""
    # Arrange
    mock_instance = AsyncMock()
    mock_client_class.return_value = mock_instance
    await telegram_manager.setup(settings)

    text_post = MagicMock(spec=TelegramPost)
    text_post.text = "Hello world"
    text_post.attachments = []

    tg_config = MagicMock(spec=TelegramConfig)
    tg_config.channel_ids = [12345]

    telegram_manager._upload_media_to_saved = AsyncMock(return_value=([], []))
    telegram_manager._send_text_to_channel = AsyncMock()

    # Act
    await telegram_manager.post_to_channels(tg_config, [text_post])

    # Assert
    telegram_manager._upload_media_to_saved.assert_awaited_once_with(text_post.attachments)
    telegram_manager._send_text_to_channel.assert_awaited_once_with(12345, "Hello world")


@pytest.mark.asyncio
@patch("src.reposter.managers.telegram_manager.Client")
async def test_post_to_channels_with_media(
    mock_client_class: MagicMock, telegram_manager: TelegramManager, settings: Settings
):
    """Tests posting a message with media attachments."""
    # Arrange
    mock_instance = AsyncMock()
    mock_client_class.return_value = mock_instance
    await telegram_manager.setup(settings)

    media_post = MagicMock(spec=TelegramPost)
    media_post.text = "Hello media"
    media_post.attachments = [MagicMock()]

    tg_config = MagicMock(spec=TelegramConfig)
    tg_config.channel_ids = [12345]

    mock_uploaded_items = [MagicMock(spec=InputMediaPhoto)]
    mock_temp_ids = [999]

    telegram_manager._upload_media_to_saved = AsyncMock(return_value=(mock_uploaded_items, mock_temp_ids))
    telegram_manager._forward_media_to_channel = AsyncMock()
    telegram_manager._delete_temp_messages = AsyncMock()
    telegram_manager._prepare_caption = MagicMock(return_value=("Hello media", None))

    # Act
    await telegram_manager.post_to_channels(tg_config, [media_post])

    # Assert
    telegram_manager._upload_media_to_saved.assert_awaited_once_with(media_post.attachments)
    telegram_manager._forward_media_to_channel.assert_awaited_once_with(12345, mock_uploaded_items, None)
    telegram_manager._delete_temp_messages.assert_awaited_once_with(mock_temp_ids)


@pytest.mark.parametrize(
    "caption, expected_caption, expected_separate_text",
    [
        ("Short caption", "Short caption", None),
        ("a" * 4097, "", "a" * 4097),
    ],
)
def test__prepare_caption(
    telegram_manager: TelegramManager, caption: str, expected_caption: str, expected_separate_text: str | None
):
    """Tests that captions are split correctly based on their length."""
    # Act
    actual_caption, actual_separate_text = telegram_manager._prepare_caption(caption)

    # Assert
    assert actual_caption == expected_caption
    assert actual_separate_text == expected_separate_text


def test__assign_caption_to_group(telegram_manager: TelegramManager):
    """Tests that a caption is assigned to the first appropriate media item."""
    # Arrange
    media_photo = MagicMock(spec=InputMediaPhoto)
    media_video = MagicMock(spec=InputMediaVideo)
    media_audio = MagicMock(spec=InputMediaAudio)
    media_doc = MagicMock(spec=InputMediaDocument)

    media_photo.caption = None
    media_video.caption = None
    media_audio.caption = None
    media_doc.caption = None

    items = [media_doc, media_audio, media_photo, media_video]
    caption = "Test Caption"

    # Act
    telegram_manager._assign_caption_to_group(items, caption)

    # Assert
    assert media_photo.caption == caption
    assert media_video.caption is None
    assert media_audio.caption is None
    assert media_doc.caption is None


@pytest.mark.asyncio
async def test__send_text_to_channel_success(telegram_manager: TelegramManager):
    """Tests successful text message sending."""
    # Arrange
    telegram_manager._client = AsyncMock()

    # Act
    await telegram_manager._send_text_to_channel(123, "Test Text")

    # Assert
    telegram_manager._client.send_message.assert_awaited_once_with(chat_id=123, text="Test Text")


@pytest.mark.asyncio
async def test__send_text_to_channel_raises_error(telegram_manager: TelegramManager):
    """Tests that a TelegramManagerError is raised on send failure."""
    # Arrange
    telegram_manager._client = AsyncMock()
    telegram_manager._client.send_message.side_effect = Exception("Send failed")

    # Act & Assert
    with pytest.raises(TelegramManagerError, match="Ошибка при отправке текста в канал 123: Send failed"):
        await telegram_manager._send_text_to_channel(123, "Test Text")


@pytest.mark.asyncio
async def test__delete_temp_messages_success(telegram_manager: TelegramManager):
    """Tests successful deletion of temporary messages."""
    # Arrange
    telegram_manager._client = AsyncMock()

    # Act
    await telegram_manager._delete_temp_messages([1, 2, 3])

    # Assert
    telegram_manager._client.delete_messages.assert_awaited_once_with(chat_id="me", message_ids=[1, 2, 3])


@pytest.mark.asyncio
async def test__delete_temp_messages_exception(telegram_manager: TelegramManager):
    """Tests that exceptions during message deletion are handled gracefully."""
    # Arrange
    telegram_manager._client = AsyncMock()
    telegram_manager._client.delete_messages.side_effect = Exception("Delete failed")

    # Act & Assert
    # Should not raise an exception
    await telegram_manager._delete_temp_messages([1, 2, 3])


@pytest.mark.asyncio
async def test__upload_media_to_saved_photo_success(telegram_manager: TelegramManager):
    """Tests the successful upload of a photo attachment."""
    # Arrange
    mock_client = AsyncMock()
    telegram_manager._client = mock_client

    attachment = MagicMock(spec=PreparedPhotoAttachment)
    attachment.filename = "test.jpg"
    attachment.file_path = "/path/to/test.jpg"

    mock_message = AsyncMock()
    mock_message.id = 999
    mock_message.photo.file_id = "file_id_123"

    mock_client.send_photo.return_value = mock_message
    telegram_manager._create_progress_callback = MagicMock()

    # Act
    uploaded_items, temp_ids = await telegram_manager._upload_media_to_saved([attachment])

    # Assert
    mock_client.send_photo.assert_awaited_once_with(
        chat_id="me",
        photo="/path/to/test.jpg",
        progress=telegram_manager._create_progress_callback.return_value,
    )
    assert len(uploaded_items) == 1
    assert isinstance(uploaded_items[0], InputMediaPhoto)
    assert uploaded_items[0].media == "file_id_123"
    assert temp_ids == [999]


@pytest.mark.asyncio
@patch("src.reposter.managers.telegram_manager.Client")
async def test_setup_cancelled_error(
    mock_client_class: MagicMock, telegram_manager: TelegramManager, settings: Settings
):
    """Tests that setup handles CancelledError properly."""
    # Arrange
    mock_instance = AsyncMock()
    mock_instance.start.side_effect = asyncio.CancelledError()
    mock_client_class.return_value = mock_instance

    # Act & Assert
    with pytest.raises(asyncio.CancelledError):
        await telegram_manager.setup(settings)
    assert not telegram_manager._initialized


@pytest.mark.asyncio
async def test_context_manager(telegram_manager: TelegramManager):
    """Tests the async context manager functionality."""
    # Arrange
    telegram_manager.shutdown = AsyncMock()
    telegram_manager._initialized = True

    # Act
    async with telegram_manager as mgr:
        assert mgr is telegram_manager

    # Assert
    telegram_manager.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_shutdown_event(telegram_manager: TelegramManager):
    """Tests that set_shutdown_event works correctly."""
    # Arrange
    event = asyncio.Event()

    # Act
    telegram_manager.set_shutdown_event(event)

    # Assert
    assert telegram_manager._shutdown_event is event


@pytest.mark.asyncio
async def test__upload_media_to_saved_video_success(telegram_manager: TelegramManager):
    """Tests the successful upload of a video attachment."""
    # Arrange
    mock_client = AsyncMock()
    telegram_manager._client = mock_client

    attachment = MagicMock(spec=PreparedVideoAttachment)
    attachment.filename = "test.mp4"
    attachment.file_path = "/path/to/test.mp4"
    attachment.width = 1920
    attachment.height = 1080
    attachment.thumbnail_path = "/path/to/thumb.jpg"

    mock_message = AsyncMock()
    mock_message.id = 999
    mock_message.video.file_id = "file_id_456"

    mock_client.send_video.return_value = mock_message
    telegram_manager._create_progress_callback = MagicMock()

    # Act
    uploaded_items, temp_ids = await telegram_manager._upload_media_to_saved([attachment])

    # Assert
    mock_client.send_video.assert_awaited_once_with(
        chat_id="me",
        video="/path/to/test.mp4",
        file_name="test.mp4",
        width=1920,
        height=1080,
        thumb="/path/to/thumb.jpg",
        progress=telegram_manager._create_progress_callback.return_value,
    )
    assert len(uploaded_items) == 1
    assert isinstance(uploaded_items[0], InputMediaVideo)
    assert uploaded_items[0].media == "file_id_456"
    assert temp_ids == [999]


@pytest.mark.asyncio
async def test__upload_media_to_saved_audio_success(telegram_manager: TelegramManager):
    """Tests the successful upload of an audio attachment."""
    # Arrange
    mock_client = AsyncMock()
    telegram_manager._client = mock_client

    attachment = MagicMock(spec=PreparedAudioAttachment)
    attachment.filename = "test.mp3"
    attachment.file_path = "/path/to/test.mp3"
    attachment.artist = "Test Artist"
    attachment.title = "Test Title"

    mock_message = AsyncMock()
    mock_message.id = 999
    mock_message.audio.file_id = "file_id_789"

    mock_client.send_audio.return_value = mock_message
    telegram_manager._create_progress_callback = MagicMock()

    # Act
    uploaded_items, temp_ids = await telegram_manager._upload_media_to_saved([attachment])

    # Assert
    mock_client.send_audio.assert_awaited_once_with(
        chat_id="me",
        audio="/path/to/test.mp3",
        file_name="test.mp3",
        performer="Test Artist",
        title="Test Title",
        progress=telegram_manager._create_progress_callback.return_value,
    )
    assert len(uploaded_items) == 1
    assert isinstance(uploaded_items[0], InputMediaAudio)
    assert uploaded_items[0].media == "file_id_789"
    assert temp_ids == [999]


@pytest.mark.asyncio
async def test__upload_media_to_saved_document_success(telegram_manager: TelegramManager):
    """Tests the successful upload of a document attachment."""
    # Arrange
    mock_client = AsyncMock()
    telegram_manager._client = mock_client

    attachment = MagicMock(spec=PreparedDocumentAttachment)
    attachment.filename = "test.doc"
    attachment.file_path = "/path/to/test.doc"

    mock_message = AsyncMock()
    mock_message.id = 999
    mock_message.document.file_id = "file_id_000"

    mock_client.send_document.return_value = mock_message
    telegram_manager._create_progress_callback = MagicMock()

    # Act
    uploaded_items, temp_ids = await telegram_manager._upload_media_to_saved([attachment])

    # Assert
    mock_client.send_document.assert_awaited_once_with(
        chat_id="me",
        document="/path/to/test.doc",
        file_name="test.doc",
        progress=telegram_manager._create_progress_callback.return_value,
    )
    assert len(uploaded_items) == 1
    assert isinstance(uploaded_items[0], InputMediaDocument)
    assert uploaded_items[0].media == "file_id_000"
    assert temp_ids == [999]


@pytest.mark.asyncio
async def test__upload_media_to_saved_with_floodwait_retry(telegram_manager: TelegramManager):
    """Tests upload retry on FloodWait exception."""
    # Arrange
    mock_client = AsyncMock()
    telegram_manager._client = mock_client

    attachment = MagicMock(spec=PreparedPhotoAttachment)
    attachment.filename = "test.jpg"
    attachment.file_path = "/path/to/test.jpg"

    # Make it fail on first attempt, succeed on second
    mock_client.send_photo.side_effect = [
        FloodWait(5),
        MagicMock(spec=Message, id=999, photo=MagicMock(file_id="file_id_123")),
    ]
    telegram_manager._handle_floodwait = AsyncMock()
    telegram_manager._create_progress_callback = MagicMock()

    # Act
    uploaded_items, temp_ids = await telegram_manager._upload_media_to_saved([attachment])

    # Assert
    assert mock_client.send_photo.call_count == 2
    assert len(uploaded_items) == 1
    assert temp_ids == [999]


@pytest.mark.asyncio
async def test__upload_media_to_saved_with_rpc_error_retry(telegram_manager: TelegramManager):
    """Tests upload retry on RPCError exception."""
    # Arrange
    mock_client = AsyncMock()
    telegram_manager._client = mock_client

    attachment = MagicMock(spec=PreparedPhotoAttachment)
    attachment.filename = "test.jpg"
    attachment.file_path = "/path/to/test.jpg"

    # Make it fail on first attempt, succeed on second
    mock_client.send_photo.side_effect = [
        Exception("Unknown error"),
        MagicMock(spec=Message, id=999, photo=MagicMock(file_id="file_id_123")),
    ]
    telegram_manager._sleep_cancelable = AsyncMock()
    telegram_manager._create_progress_callback = MagicMock()

    # Act
    uploaded_items, temp_ids = await telegram_manager._upload_media_to_saved([attachment])

    # Assert
    assert mock_client.send_photo.call_count == 2
    assert len(uploaded_items) == 1
    assert temp_ids == [999]


@pytest.mark.asyncio
async def test__upload_media_to_saved_max_retries_exceeded(telegram_manager: TelegramManager):
    """Tests that upload fails after max retries exceeded."""
    # Arrange
    mock_client = AsyncMock()
    telegram_manager._client = mock_client

    attachment = MagicMock(spec=PreparedPhotoAttachment)
    attachment.filename = "test.jpg"
    attachment.file_path = "/path/to/test.jpg"

    # Always fail
    mock_client.send_photo.side_effect = Exception("Always fails")
    telegram_manager._sleep_cancelable = AsyncMock()
    telegram_manager._create_progress_callback = MagicMock()

    # Act & Assert
    with pytest.raises(TelegramManagerError, match="Не удалось загрузить вложение test.jpg после 3 попыток."):
        await telegram_manager._upload_media_to_saved([attachment])


@pytest.mark.asyncio
async def test__forward_media_to_channel_with_media_groups(telegram_manager: TelegramManager):
    """Tests sending media in groups."""
    # Arrange
    mock_client = AsyncMock()
    telegram_manager._client = mock_client

    photo1 = MagicMock(spec=InputMediaPhoto)
    photo1.media = "photo1_id"
    photo2 = MagicMock(spec=InputMediaPhoto)
    photo2.media = "photo2_id"
    video1 = MagicMock(spec=InputMediaVideo)
    video1.media = "video1_id"
    audio1 = MagicMock(spec=InputMediaAudio)
    audio1.media = "audio1_id"
    audio2 = MagicMock(spec=InputMediaAudio)
    audio2.media = "audio2_id"
    doc1 = MagicMock(spec=InputMediaDocument)
    doc1.media = "doc1_id"
    doc2 = MagicMock(spec=InputMediaDocument)
    doc2.media = "doc2_id"

    uploaded_items = [photo1, photo2, video1, audio1, audio2, doc1, doc2]

    # Act
    await telegram_manager._forward_media_to_channel(12345, uploaded_items, None)

    # Assert
    # Photo + video group (3 items total, but only 2 photos + 1 video)
    mock_client.send_media_group.assert_any_call(chat_id=12345, media=[photo1, photo2, video1])
    # Audio group (2 items)
    mock_client.send_media_group.assert_any_call(chat_id=12345, media=[audio1, audio2])
    # Document group (2 items)
    mock_client.send_media_group.assert_any_call(chat_id=12345, media=[doc1, doc2])


@pytest.mark.asyncio
async def test__forward_media_to_channel_separate_items(telegram_manager: TelegramManager):
    """Tests sending media as separate items."""
    # Arrange
    mock_client = AsyncMock()
    telegram_manager._client = mock_client

    photo1 = MagicMock(spec=InputMediaPhoto)
    photo1.media = "photo1_id"
    photo1.caption = None
    audio1 = MagicMock(spec=InputMediaAudio)
    audio1.media = "audio1_id"
    audio1.caption = None
    doc1 = MagicMock(spec=InputMediaDocument)
    doc1.media = "doc1_id"
    doc1.caption = None

    uploaded_items = [photo1, audio1, doc1]

    # Act
    await telegram_manager._forward_media_to_channel(12345, uploaded_items, None)

    # Assert
    mock_client.send_photo.assert_awaited_once_with(chat_id=12345, photo="photo1_id", caption=None)
    mock_client.send_audio.assert_awaited_once_with(chat_id=12345, audio="audio1_id", caption=None)
    mock_client.send_document.assert_awaited_once_with(chat_id=12345, document="doc1_id", caption=None)
    # send_media_group should not have been called since each group has only 1 item
    mock_client.send_media_group.assert_not_called()


@pytest.mark.asyncio
async def test__forward_media_to_channel_with_separate_text(telegram_manager: TelegramManager):
    """Tests sending media with separate text."""
    # Arrange
    mock_client = AsyncMock()
    telegram_manager._client = mock_client
    telegram_manager._send_text_to_channel = AsyncMock()

    photo1 = MagicMock(spec=InputMediaPhoto)
    photo1.media = "photo1_id"
    photo1.caption = None
    uploaded_items = [photo1]

    # Act
    await telegram_manager._forward_media_to_channel(12345, uploaded_items, "Separate text message")

    # Assert
    mock_client.send_photo.assert_awaited_once_with(chat_id=12345, photo="photo1_id", caption=None)
    telegram_manager._send_text_to_channel.assert_awaited_once_with(12345, "Separate text message")


@pytest.mark.asyncio
async def test__forward_media_to_channel_exceptions(telegram_manager: TelegramManager):
    """Tests exception handling in _forward_media_to_channel."""
    # Arrange
    mock_client = AsyncMock()
    mock_client.send_photo.side_effect = ChannelPrivate("Channel is private")
    telegram_manager._client = mock_client

    photo1 = MagicMock(spec=InputMediaPhoto)
    photo1.media = "photo1_id"
    photo1.caption = None
    uploaded_items = [photo1]

    # Act & Assert (should not raise an exception)
    await telegram_manager._forward_media_to_channel(12345, uploaded_items, None)


@pytest.mark.asyncio
async def test__forward_media_to_channel_other_exception(telegram_manager: TelegramManager):
    """Tests other exceptions in _forward_media_to_channel."""
    # Arrange
    mock_client = AsyncMock()
    mock_client.send_photo.side_effect = Exception("Other error")
    telegram_manager._client = mock_client

    photo1 = MagicMock(spec=InputMediaPhoto)
    photo1.media = "photo1_id"
    photo1.caption = None
    uploaded_items = [photo1]

    # Act & Assert
    with pytest.raises(TelegramManagerError, match=r"Ошибка при отправке в канал 12345:.*Other error"):
        await telegram_manager._forward_media_to_channel(12345, uploaded_items, None)


def test__assign_caption_to_group_audio_priority(telegram_manager: TelegramManager):
    """Tests that a caption is assigned to the first audio item if no photo/video."""
    # Arrange
    media_audio = MagicMock(spec=InputMediaAudio)
    media_doc = MagicMock(spec=InputMediaDocument)

    media_audio.caption = None
    media_doc.caption = None

    items = [media_doc, media_audio]  # No photos or videos
    caption = "Test Caption"

    # Act
    telegram_manager._assign_caption_to_group(items, caption)

    # Assert
    assert media_audio.caption == caption
    assert media_doc.caption is None


def test__assign_caption_to_group_document_priority(telegram_manager: TelegramManager):
    """Tests that a caption is assigned to the first document item if no photo/video or audio."""
    # Arrange
    media_doc1 = MagicMock(spec=InputMediaDocument)
    media_doc2 = MagicMock(spec=InputMediaDocument)

    media_doc1.caption = None
    media_doc2.caption = None

    items = [media_doc1, media_doc2]  # Only documents
    caption = "Test Caption"

    # Act
    telegram_manager._assign_caption_to_group(items, caption)

    # Assert
    assert media_doc1.caption == caption
    assert media_doc2.caption is None


@pytest.mark.asyncio
async def test__handle_floodwait(telegram_manager: TelegramManager):
    """Tests the _handle_floodwait functionality."""
    # Arrange
    telegram_manager._sleep_cancelable = AsyncMock()

    # Act
    await telegram_manager._handle_floodwait(FloodWait(10))

    # Assert
    telegram_manager._sleep_cancelable.assert_awaited_once_with(11)  # 10 + 1


@pytest.mark.asyncio
async def test__handle_floodwait_non_int_value(telegram_manager: TelegramManager):
    """Tests the _handle_floodwait with non-integer value."""
    # Arrange
    telegram_manager._sleep_cancelable = AsyncMock()
    floodwait = FloodWait("timeout")  # String value instead of int

    # Act
    await telegram_manager._handle_floodwait(floodwait)

    # Assert
    telegram_manager._sleep_cancelable.assert_awaited_once_with(61)  # Default to 60 + 1


@pytest.mark.asyncio
async def test__sleep_cancelable(telegram_manager: TelegramManager):
    """Tests the _sleep_cancelable functionality."""
    # Arrange
    telegram_manager._check_shutdown = MagicMock()

    # Act
    await telegram_manager._sleep_cancelable(1)  # Sleep for 1 second

    # Assert - Just check that it completes without error
    # _check_shutdown should be called multiple times during the sleep
    assert telegram_manager._check_shutdown.call_count > 0


@pytest.mark.asyncio
async def test__sleep_cancelable_with_shutdown(telegram_manager: TelegramManager):
    """Tests the _sleep_cancelable functionality with shutdown check raising exception."""
    # Arrange
    telegram_manager._check_shutdown = MagicMock(side_effect=Exception("Shutdown"))

    # Act & Assert
    with pytest.raises(Exception, match="Shutdown"):
        await telegram_manager._sleep_cancelable(1)
