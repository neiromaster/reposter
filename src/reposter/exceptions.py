"""Custom exceptions for the application."""


class PostProcessingError(Exception):
    """Custom exception for errors during post processing."""

    pass


class SkipPostException(Exception):
    """Custom exception to indicate that a post should be skipped."""

    pass


class TelegramManagerError(Exception):
    """Custom exception for errors during Telegram processing."""

    pass


class VKApiError(Exception):
    """Custom exception for errors returned by the VK API."""

    pass


class BoostyPublicationError(Exception):
    """Custom exception for errors during Boosty post creation."""

    pass
