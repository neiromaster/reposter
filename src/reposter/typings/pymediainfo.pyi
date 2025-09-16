# Stubs for pymediainfo
from typing import Any

class Track:
    # Common fields for all track types
    track_type: str
    def to_data(self) -> dict[str, Any]: ...

    # General track
    file_name: str | None
    file_extension: str | None
    complete_name: str | None
    folder_name: str | None
    file_size: int | None
    overall_bit_rate: int | None
    overall_bit_rate_mode: str | None
    duration: float | None
    format: str | None
    format_version: str | None
    format_profile: str | None
    encoded_date: str | None
    tagged_date: str | None
    file_last_modification_date: str | None
    file_last_modification_date__local: str | None

    # Video
    width: int | None
    height: int | None
    pixel_aspect_ratio: float | None
    display_aspect_ratio: float | None
    frame_rate: float | None
    frame_rate_mode: str | None
    frame_count: int | None
    bit_rate: int | None
    bit_rate_mode: str | None
    color_space: str | None
    chroma_subsampling: str | None
    bit_depth: int | None
    scan_type: str | None
    codec_id: str | None
    codec_id_info: str | None
    codec_id_hint: str | None
    codec_id_url: str | None
    codec_id_description: str | None
    codec_family: str | None
    codec_info: str | None
    codec_url: str | None
    codec_cc: str | None
    codec_profile: str | None
    codec_settings: str | None
    codec_settings__cabac: str | None
    codec_settings__reft_frames: str | None
    encoded_library: str | None
    encoded_library_name: str | None
    encoded_library_version: str | None
    encoded_library_settings: str | None
    language: str | None
    default: str | None
    forced: str | None

    # Audio
    channels: int | None
    channel_positions: str | None
    channel_layout: str | None
    sampling_rate: int | None
    sampling_count: int | None
    compression_mode: str | None
    stream_size: int | None
    album: str | None
    performer: str | None
    track_name: str | None
    track_name_position: int | None
    track_name_total: int | None
    genre: str | None
    recorded_date: str | None
    writing_library: str | None
    writing_library_name: str | None
    writing_library_version: str | None
    writing_library_settings: str | None

    # Images
    color_space: str | None
    chroma_subsampling: str | None
    bit_depth: int | None
    compression_mode: str | None

class MediaInfo:
    tracks: list[Track]
    video_tracks: list[Track]
    audio_tracks: list[Track]
    image_tracks: list[Track]
    general_tracks: list[Track]

    @classmethod
    def parse(cls, filename: str) -> MediaInfo: ...
