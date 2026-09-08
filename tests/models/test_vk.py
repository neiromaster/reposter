"""Tests for VK response models tolerance to new VK API data shapes."""

import pytest
from pydantic import ValidationError

from reposter.models.vk import Attachment, WallGetResponse


def _minimal_post(item_id: int) -> dict[str, object]:
    return {
        "id": item_id,
        "owner_id": -12345,
        "from_id": -12345,
        "date": 1757350000,
        "text": "test post",
    }


def _photo() -> dict[str, object]:
    size: dict[str, str | int] = {"type": "x", "url": "https://vk.ru/img.jpg", "width": 100, "height": 100}
    return {"id": 1, "owner_id": -1, "sizes": [size], "orig_photo": size}


class TestAttachmentType:
    def test_known_types_still_validate(self) -> None:
        for att_type in ("photo", "video", "doc", "link", "poll", "audio", "graffiti", "donut_link"):
            assert Attachment(type=att_type).type == att_type

    def test_unknown_attachment_type_does_not_raise(self) -> None:
        attachment = Attachment(type="action_button")
        assert attachment.type == "action_button"


class TestWallGetResponse:
    def test_ad_items_are_dropped(self) -> None:
        data: dict[str, list[dict[str, object]]] = {
            "items": [
                _minimal_post(101),
                {"type": "ads", "ads_title": "Ad title", "ads_marker": "2VtzqvoJb7R"},
                _minimal_post(102),
            ]
        }
        response = WallGetResponse.model_validate(data)
        assert [post.id for post in response.items] == [101, 102]

    def test_post_with_action_button_attachment(self) -> None:
        data: dict[str, list[dict[str, object]]] = {
            "items": [
                {
                    **_minimal_post(103),
                    "attachments": [
                        {"type": "action_button", "action": {"title": "Join"}},
                        {"type": "photo", "photo": _photo()},
                    ],
                }
            ]
        }
        response = WallGetResponse.model_validate(data)
        assert [a.type for a in response.items[0].attachments] == ["action_button", "photo"]

    def test_unrelated_validation_errors_still_raise(self) -> None:
        data: dict[str, list[dict[str, object]]] = {"items": [{"id": 1, "owner_id": -1, "from_id": -1, "date": 1}]}
        with pytest.raises(ValidationError):
            WallGetResponse.model_validate(data)
