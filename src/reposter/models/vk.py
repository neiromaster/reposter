from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


class PhotoSize(BaseModel):
    type: str
    url: HttpUrl
    width: int
    height: int


class Photo(BaseModel):
    id: int
    owner_id: int
    sizes: list[PhotoSize]
    orig_photo: PhotoSize

    @property
    def max_size_url(self) -> HttpUrl:
        if not self.sizes:
            raise ValueError("Photo has no sizes")
        return max(self.sizes, key=lambda size: size.width).url


class CoverSize(BaseModel):
    url: HttpUrl
    width: int
    height: int
    with_padding: int | None = None


class Video(BaseModel):
    id: int
    owner_id: int
    title: str
    description: str | None = None
    duration: int | None = None
    access_key: str | None = None
    image: list[CoverSize] | None = None

    @property
    def max_size_url(self) -> HttpUrl | None:
        if not self.image:
            return None
        return max(self.image, key=lambda size: size.width).url

    @property
    def url(self) -> str:
        return f"https://vk.com/video{self.owner_id}_{self.id}"


class Audio(BaseModel):
    id: int
    owner_id: int
    title: str
    artist: str
    url: HttpUrl


class Doc(BaseModel):
    id: int
    owner_id: int
    title: str
    url: HttpUrl


class Link(BaseModel):
    title: str
    url: HttpUrl
    description: str


class PollAnswer(BaseModel):
    id: int
    text: str


class Poll(BaseModel):
    id: int
    owner_id: int
    question: str
    multiple: bool
    answers: list[PollAnswer]


class DonutLink(BaseModel):
    owner_id: int


class Attachment(BaseModel):
    type: Literal["photo", "video", "doc", "link", "poll", "audio", "graffiti", "donut_link"]
    photo: Photo | None = None
    video: Video | None = None
    doc: Doc | None = None
    link: Link | None = None
    poll: Poll | None = None
    audio: Audio | None = None
    graffiti: dict[str, Any] | None = None
    donut_link: DonutLink | None = None


class Post(BaseModel):
    id: int
    owner_id: int
    from_id: int
    date: int
    text: str
    attachments: list[Attachment] = []
    is_pinned: int | None = Field(None)


class WallGetResponse(BaseModel):
    items: list[Post]
