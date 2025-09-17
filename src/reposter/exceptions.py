"""Custom exceptions for the application."""


class PostProcessingError(Exception):
    """Custom exception for errors during post processing."""

    pass


class TelegramManagerError(Exception):
    """Custom exception for errors during Telegram processing."""

    pass
