import pytest

from src.reposter.utils.text_utils import extract_tags_from_text


@pytest.mark.parametrize(
    ("text", "expected_tags"),
    [
        (
            """Пламя ночи - 69 серия из 80 (русская озвучка)(2025)[DubLikTV]
Плейлист ВК vkvideo.ru/playlist/-51712074_55470139
Переведено: Азалия Сидоренко (http://vk.com/id648571755)
Озвучено: #Chill #Asya
#пламя_ночи #пламя_ночи_2025""",
            ["пламя ночи", "пламя ночи 2025"],
        ),
        (
            """Пламя ночи - 69 серия из 80 (русская озвучка)(2025)[DubLikTV]
Плейлист ВК vkvideo.ru/playlist/-51712074_55470139
Переведено: Азалия Сидоренко (http://vk.com/id648571755)
Озвучено: #Chill #Asya #пламя_ночи #пламя_ночи_2025""",
            [],
        ),
        (
            """Пламя ночи - 69 серия из 80 (русская озвучка)(2025)[DubLikTV]
Плейлист ВК vkvideo.ru/playlist/-51712074_55470139
Переведено: Азалия Сидоренко (http://vk.com/id648571755)
Озвучено: Chill Asya""",
            [],
        ),
        (
            """Пламя ночи - 69 серия из 80 (русская озвучка)(2025)[DubLikTV]
#пламя_ночи #пламя_ночи_2025
Плейлист ВК vkvideo.ru/playlist/-51712074_55470139
Переведено: Азалия Сидоренко (http://vk.com/id648571755)
Озвучено: #Chill #Asya""",
            [],
        ),
        (
            "",
            [],
        ),
        (
            "#tag1 #tag2",
            ["tag1", "tag2"],
        ),
        (
            "Some text #tag1 #tag2",
            [],
        ),
        (
            """#tag1 #tag2
Some text""",
            [],
        ),
        (
            """Line 1
#tag1 #tag2
Line 3""",
            [],
        ),
    ],
)
def test_extract_tags_from_text(text: str, expected_tags: list[str]):
    tags = extract_tags_from_text(text)
    assert tags == expected_tags
