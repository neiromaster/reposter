import re
from pathlib import Path
from re import Match
from urllib.parse import urlparse

import emoji

PATTERN_BRACKET_LINK = r"\[([^\]|]+)\|([^\]]+)\]"
PATTERN_PROTOCOL_URL = r"https?://[^\s\]]+"


def normalize_links(text: str) -> str:
    """Normalize links in the text, handling VK-specific formats and emojis."""

    def insert_zwsp_after_emoji_sequences(s: str) -> str:
        """Insert a zero-width space after emoji sequences to prevent them from sticking."""
        emjs = emoji.emoji_list(s)
        if not emjs:
            return s
        result: list[str] = []
        last_idx = 0
        for e in emjs:
            start, end = e["match_start"], e["match_end"]
            result.append(s[last_idx:start])
            result.append(s[start:end] + "\u200b")  # Zero-width space
            last_idx = end
        result.append(s[last_idx:])
        return "".join(result)

    text = insert_zwsp_after_emoji_sequences(text)

    def replace_bracket_link(match: Match[str]) -> str:
        """Handle [link|label] style links."""
        link = match.group(1).strip()
        label = match.group(2).strip()

        if re.fullmatch(r"(club\d+|id\d+)", link):
            return f"[{label}](vk.com/{link})"

        if link.startswith("vk.com/") and re.match(r"https?://", label):
            parsed = urlparse(label)
            return parsed.netloc + (parsed.path if parsed.path != "/" else "")

        if re.match(r"https?://", label):
            parsed = urlparse(label)
            if parsed.scheme in ("http", "https") and parsed.netloc:
                return parsed.netloc + (parsed.path if parsed.path != "/" else "")

        if re.match(r"https?://", link):
            parsed = urlparse(link)
            if parsed.scheme in ("http", "https") and parsed.netloc:
                clean_link = parsed.netloc + (parsed.path if parsed.path != "/" else "")
                return f"[{label}]({clean_link})"
            else:
                return label

        if re.match(r"^[\w.-]+\.[a-z]{2,}", link):
            return f"[{label}]({link})"

        return label

    text = re.sub(PATTERN_BRACKET_LINK, replace_bracket_link, text)

    def strip_protocol(match: Match[str]) -> str:
        """Remove http/https from a URL for cleaner display."""
        url = match.group(0)
        parsed = urlparse(url)
        if parsed.scheme in ("http", "https"):
            return parsed.netloc + (parsed.path if parsed.path != "/" else "")
        return url

    text = re.sub(PATTERN_PROTOCOL_URL, strip_protocol, text)

    return text


def sanitize_filename(filename: str) -> str:
    """Removes characters that are invalid for filenames in Windows and Linux."""
    # Replace forward and backslashes with a space
    filename = re.sub(r"[\/]", " ", filename)
    # Characters invalid in Windows and/or Linux filenames
    # ASCII 0-31 are control characters, also handled
    invalid_chars = r'[:*?"<>|]'
    # Replace invalid characters with an underscore
    sanitized = re.sub(invalid_chars, "_", filename)
    # Replace control characters
    sanitized = re.sub(r"[\x00-\x1f]", "", sanitized)
    # Reduce multiple spaces to a single space
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    # Reduce multiple underscores to a single one
    sanitized = re.sub(r"_+", "_", sanitized)
    # It's also a good idea to limit the filename length
    return sanitized[:200]  # Limit to 200 chars as a safe measure


def sanitize_for_telegram(filename: str) -> str:
    """Sanitizes filename for Telegram by replacing brackets with spaces."""
    sanitized = re.sub(r"[\[\]()]", " ", filename)
    sanitized = re.sub(r"\s+", " ", sanitized)
    return sanitized.strip()


def sanitize_filename_for_telegram(raw_filename: str) -> str:
    """Sanitizes a filename for Telegram, preserving the extension."""
    p = Path(raw_filename)
    name = p.stem
    ext = p.suffix
    sanitized_name = sanitize_filename(name)
    sanitized_name = sanitize_for_telegram(sanitized_name)
    return sanitized_name + ext


def extract_tags_from_text(text: str) -> list[str]:
    """Extracts tags from the last line of the text."""
    if not text:
        return []

    lines = text.strip().splitlines()
    if not lines:
        return []

    last_line = lines[-1].strip()
    if not last_line:
        return []

    words = last_line.split()
    if not words:
        return []

    if not all(word.startswith("#") for word in words):
        return []

    return [word.lstrip("#").replace("_", " ") for word in words]
