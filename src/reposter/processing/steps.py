from abc import ABC, abstractmethod
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
    DownloadedArtifact,
    PreparedAudioAttachment,
    PreparedDocumentAttachment,
    PreparedPhotoAttachment,
    PreparedVideoAttachment,
    TelegramPost,
)
from ..models.dto import (
    Photo as VkPhoto,
)
from ..models.dto import (
    Post as VkPost,
)
from ..models.dto import (
    Video as VkVideo,
)
from ..utils.log import log
from ..utils.text_utils import extract_tags_from_text, normalize_links


class ProcessingStep(ABC):
    @abstractmethod
    async def process(self, post: VkPost, prepared_post: TelegramPost) -> None:
        pass


class LinkNormalizationStep(ProcessingStep):
    async def process(self, post: VkPost, prepared_post: TelegramPost) -> None:
        prepared_post.text = normalize_links(prepared_post.text)


class TagExtractionStep(ProcessingStep):
    async def process(self, post: VkPost, prepared_post: TelegramPost) -> None:
        tags = extract_tags_from_text(prepared_post.text)
        if tags:
            prepared_post.tags = tags
            prepared_post.text = "\n".join(prepared_post.text.splitlines()[:-1]).strip()


class AttachmentDownloaderStep(ProcessingStep):
    def __init__(self, vk_manager: VKManager, ytdlp_manager: YTDLPManager) -> None:
        self.vk = vk_manager
        self.ytdlp = ytdlp_manager

    async def process(self, post: VkPost, prepared_post: TelegramPost) -> None:
        for attachment in post.attachments:
            downloaded_artifact = None
            match attachment.type:
                case "video":
                    if attachment.video:
                        downloaded_artifact = await self._download_video(attachment.video)
                case "photo":
                    if attachment.photo:
                        downloaded_artifact = await self._download_photo(attachment.photo)
                case "audio":
                    if attachment.audio:
                        downloaded_artifact = await self._download_audio(attachment.audio)
                case "doc":
                    if attachment.doc:
                        downloaded_artifact = await self._download_doc(attachment.doc)
                case "poll" | "link" | "graffiti" | "donut_link":
                    log(f"🚫 Пропускаю неподдерживаемое вложение типа: {attachment.type}", indent=4)
                case _:
                    log(f"❓ Неизвестный тип вложения: {attachment.type}", indent=4)

            if downloaded_artifact:
                prepared_post.downloaded_artifacts.append(downloaded_artifact)

    async def _download_video(self, video: VkVideo) -> DownloadedArtifact:
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

        return DownloadedArtifact(
            type="video",
            original_attachment=video,
            file_path=video_path,
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

            if longer == TARGET:
                category = 0
                distance = 0
            elif longer > TARGET:
                category = 1
                distance = longer - TARGET
            else:
                category = 2
                distance = TARGET - longer

            ratio = w / h if h else 0
            ratio_diff = abs(ratio - target_ratio)

            return (category, distance, ratio_diff, -w * h)

        return sorted(candidates, key=sort_key)[0]

    async def _download_photo(self, photo: VkPhoto) -> DownloadedArtifact:
        log("📸 Обрабатываю фото...", indent=4)
        photo_path = await self.vk.download_file(photo.max_size_url, Path("downloads/photos"))
        if not photo_path:
            raise PostProcessingError("❌ Не удалось скачать фото.")

        return DownloadedArtifact(
            type="photo",
            original_attachment=photo,
            file_path=photo_path,
        )

    async def _download_audio(self, audio: VkAudio) -> DownloadedArtifact:
        log("🎵 Обрабатываю аудио...", indent=4)

        download_dir = Path("downloads/audio")
        audio_path = await self.vk.download_file(url=audio.url, download_path=download_dir)

        if not audio_path:
            raise PostProcessingError("❌ Не удалось скачать аудио.")

        return DownloadedArtifact(
            type="audio",
            original_attachment=audio,
            file_path=audio_path,
            artist=audio.artist,
            title=audio.title,
        )

    async def _download_doc(self, doc: VkDoc) -> DownloadedArtifact:
        log("📄 Обрабатываю документ...", indent=4)

        download_dir = Path("downloads/docs")
        doc_path = await self.vk.download_file(url=doc.url, download_path=download_dir)

        if not doc_path:
            raise PostProcessingError("❌ Не удалось скачать документ.")

        return DownloadedArtifact(
            type="doc",
            original_attachment=doc,
            file_path=doc_path,
            filename=doc.title,
        )


class AttachmentDtoCreationStep(ProcessingStep):
    async def process(self, post: VkPost, prepared_post: TelegramPost) -> None:
        for artifact in prepared_post.downloaded_artifacts:
            prepared_attachment = None
            match artifact.type:
                case "video":
                    if not isinstance(artifact.original_attachment, VkVideo):
                        continue
                    if artifact.width is None or artifact.height is None:
                        raise PostProcessingError("Отсутствуют размеры видео.")
                    prepared_attachment = PreparedVideoAttachment(
                        file_path=artifact.file_path,
                        filename=(
                            artifact.original_attachment.title
                            or f"{artifact.original_attachment.owner_id}_{artifact.original_attachment.id}"
                        )
                        + artifact.file_path.suffix,
                        width=artifact.width,
                        height=artifact.height,
                        thumbnail_path=artifact.thumbnail_path,
                    )
                case "photo":
                    if not isinstance(artifact.original_attachment, VkPhoto):
                        continue
                    prepared_attachment = PreparedPhotoAttachment(
                        file_path=artifact.file_path,
                        filename=artifact.file_path.stem + artifact.file_path.suffix,
                    )
                case "audio":
                    if not isinstance(artifact.original_attachment, VkAudio):
                        continue
                    if artifact.artist is None or artifact.title is None:
                        raise PostProcessingError("Отсутствуют исполнитель или название аудио.")
                    prepared_attachment = PreparedAudioAttachment(
                        file_path=artifact.file_path,
                        filename=f"{artifact.artist} - {artifact.title}" + artifact.file_path.suffix,
                        artist=artifact.artist,
                        title=artifact.title,
                    )
                case "doc":
                    if not isinstance(artifact.original_attachment, VkDoc):
                        continue
                    if artifact.filename is None:
                        raise PostProcessingError("Отсутствует имя файла документа.")
                    prepared_attachment = PreparedDocumentAttachment(
                        file_path=artifact.file_path,
                        filename=artifact.filename + artifact.file_path.suffix,
                    )

            if prepared_attachment:
                prepared_post.attachments.append(prepared_attachment)
