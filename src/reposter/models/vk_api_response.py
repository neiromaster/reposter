from __future__ import annotations

from typing import Any, NotRequired, TypedDict


class VKErrorDict(TypedDict):
    error_code: int
    error_msg: str


class WallGetResponseDict(TypedDict):
    count: int
    items: list[dict[str, Any]]


class VKAPIResponseDict(TypedDict):
    response: NotRequired[WallGetResponseDict]
    error: NotRequired[VKErrorDict]
