from pathlib import Path

from pymediainfo import MediaInfo

from ..exceptions import PostProcessingError
from ..managers.vk_manager import VKManager
from ..managers.ytdlp_manager import YTDLPManager
from ..models.dto import (
    Audio as VkAudio,
)
from ..models.dto import (
    CoverSize as VkCoverSize,
)
from ..models.dto import (
    Doc as VkDoc,
)
from ..models.dto import (
    Photo as VkPhoto,
)
from ..models.dto import (
    Post as VkPost,
)
from ..models.dto import (
    PreparedAudioAttachment,
    PreparedDocumentAttachment,
    PreparedPhotoAttachment,
    PreparedVideoAttachment,
    TelegramPost,
)
from ..models.dto import (
    Video as VkVideo,
)
from ..utils.log import log
from ..utils.text_utils import normalize_links


class PostProcessor:
    def __init__(self, vk_manager: VKManager, ytdlp_manager: YTDLPManager) -> None:
        self.vk = vk_manager
        self.ytdlp = ytdlp_manager

    async def process_post(self, post: VkPost) -> TelegramPost:
        """Converts a raw VK post into a Telegram-ready post."""
        processed_text = self._process_text(post.text)

        prepared_attachments: list[
            PreparedPhotoAttachment | PreparedVideoAttachment | PreparedAudioAttachment | PreparedDocumentAttachment
        ] = []

        for attachment in post.attachments:
            prepared_attachment = None
            match attachment.type:
                case "video":
                    if attachment.video:
                        prepared_attachment = await self._process_video(attachment.video)
                case "photo":
                    if attachment.photo:
                        prepared_attachment = await self._process_photo(attachment.photo)
                case "audio":
                    if attachment.audio:
                        prepared_attachment = await self._process_audio(attachment.audio)
                case "doc":
                    if attachment.doc:
                        prepared_attachment = await self._process_doc(attachment.doc)
                case "poll" | "link" | "graffiti" | "donut_link":
                    log(f"🚫 Пропускаю неподдерживаемое вложение типа: {attachment.type}", indent=4)
                case _:
                    log(f"❓ Неизвестный тип вложения: {attachment.type}", indent=4)

            if prepared_attachment:
                prepared_attachments.append(prepared_attachment)

        return TelegramPost(text=processed_text, attachments=prepared_attachments)

    def _process_text(self, text: str) -> str:
        return normalize_links(text)

    async def _process_video(self, video: VkVideo) -> PreparedVideoAttachment:
        log("🎬 Обрабатываю видео...", indent=4)
        video_path = await self.ytdlp.download_video(video.url)
        if not video_path:
            raise PostProcessingError("❌ Не удалось скачать видео.")

        thumb_path = None
        best_thumb = self._find_best_thumbnail(video.image)
        if best_thumb:
            log("🖼️ Скачиваю обложку...", indent=5)
            thumb_path = await self.vk.download_file(best_thumb.url, Path("downloads/thumbnails"))

        try:
            media_info = MediaInfo.parse(str(video_path))
            video_track = next((track for track in media_info.tracks if track.track_type == "Video"), None)
            if not video_track or not video_track.width or not video_track.height:
                raise PostProcessingError(
                    f"❌ Не удалось найти видео-дорожку или ее размеры в файле: {video_path.name}"
                )
            width, height = video_track.width, video_track.height
        except Exception as e:
            raise PostProcessingError(f"❌ Не удалось получить метаданные видео: {e}") from e

        return PreparedVideoAttachment(
            file_path=video_path,
            filename=(video.title or f"{video.owner_id}_{video.id}") + video_path.suffix,
            width=width,
            height=height,
            thumbnail_path=thumb_path,
        )

    def _find_best_thumbnail(self, images: list[VkCoverSize], target_ratio: float = 16 / 9) -> VkCoverSize | None:
        log("🌟 Выбираю лучшую обложку...", indent=5)
        TARGET = 1280
        if not images:
            return None

        no_pad = [img for img in images if not img.with_padding]
        pad = [img for img in images if img.with_padding]

        candidates = no_pad if no_pad else pad

        def sort_key(img: VkCoverSize) -> tuple[int, int, float, int]:
            w, h = img.width, img.height
            longer = max(w, h)

            # Category: 0 - exactly 320, 1 - more than 320, 2 - less than 320
            if longer == TARGET:
                category = 0
                distance = 0
            elif longer > TARGET:
                category = 1
                distance = longer - TARGET
            else:
                category = 2
                distance = TARGET - longer

            # Deviation from the target aspect ratio
            ratio = w / h if h else 0
            ratio_diff = abs(ratio - target_ratio)

            # Минус площадь, чтобы большее разрешение шло раньше
            return (category, distance, ratio_diff, -w * h)

        return sorted(candidates, key=sort_key)[0]

    async def _process_photo(self, photo: VkPhoto) -> PreparedPhotoAttachment:
        log("📸 Обрабатываю фото...", indent=4)
        photo_path = await self.vk.download_file(photo.max_size_url, Path("downloads/photos"))
        if not photo_path:
            raise PostProcessingError("❌ Не удалось скачать фото.")

        return PreparedPhotoAttachment(
            file_path=photo_path,
            filename=photo_path.name,
        )

    async def _process_audio(self, audio: VkAudio) -> PreparedAudioAttachment:
        log("🎵 Обрабатываю аудио...", indent=4)

        download_dir = Path("downloads/audio")
        audio_path = await self.vk.download_file(url=audio.url, download_path=download_dir)

        if not audio_path:
            raise PostProcessingError("❌ Не удалось скачать аудио.")

        # TODO: add file name sanitization for Windows/Linux
        filename = f"{audio.artist} - {audio.title}{audio_path.suffix}"

        return PreparedAudioAttachment(
            file_path=audio_path,
            filename=filename,
            artist=audio.artist,
            title=audio.title,
        )

    async def _process_doc(self, doc: VkDoc) -> PreparedDocumentAttachment:
        log("📄 Обрабатываю документ...", indent=4)

        download_dir = Path("downloads/docs")
        doc_path = await self.vk.download_file(url=doc.url, download_path=download_dir)

        if not doc_path:
            raise PostProcessingError("❌ Не удалось скачать документ.")

        filename = f"{doc.title}{doc_path.suffix}"

        return PreparedDocumentAttachment(
            file_path=doc_path,
            filename=filename,
        )
