from collections.abc import Sequence
from pathlib import Path

from ..models import PreparedAttachment, PreparedVideoAttachment
from .log import log


async def delete_files_async(attachments: Sequence[PreparedAttachment]) -> None:
    """Deletes the locally downloaded files associated with the attachments."""

    def _delete_single_file(file_path: Path, description: str) -> None:
        try:
            if file_path.exists():
                file_path.unlink()
                log(f"🧹 Удален {description}: {file_path}", indent=4)
        except FileNotFoundError:
            log(f"⚠️ {description} не найден при попытке удаления: {file_path}", indent=4)
        except Exception as e:
            log(f"❌ Ошибка при удалении {description} {file_path}: {e}", indent=4)

    for attachment in attachments:
        _delete_single_file(attachment.file_path, "файл")
        if isinstance(attachment, PreparedVideoAttachment) and attachment.thumbnail_path:
            _delete_single_file(attachment.thumbnail_path, "файл миниатюры")
