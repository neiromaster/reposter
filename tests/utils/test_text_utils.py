import pytest

from src.reposter.utils.text_utils import extract_tags_from_text, normalize_links


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


# Atomic test cases to isolate functionality
TEST_CASES = [
    # 1. Test just an emoji
    ("emoji_only", "Hello 👍 World", "Hello 👍\u200b World"),
    # 2. Test just a junk link
    ("junk_link", "Link: [vk.com/junk|http://real.com/page]", "Link: real.com/page"),
    # 3. Test just a club link
    ("club_link", "Group: [club123|My Club]", "Group: [My Club](vk.com/club123)"),
    # 4. Test just an ID link
    ("id_link", "User: [id456|My Name]", "User: [My Name](vk.com/id456)"),
    # 5. Test a valid URL link
    ("url_link", "Site: [https://example.com|My Site]", "Site: [My Site](example.com)"),
    # 6. Test a broken URL link
    ("broken_url_link", "Broken: [httpd://broken|Do not show link]", "Broken: Do not show link"),
    # 7. Test stripping protocol from a raw link
    ("protocol_strip", "Raw link: https://raw.link/path", "Raw link: raw.link/path"),
    # 8. Test emoji and a simple link
    ("emoji_and_link", "Pointer 👉[club123|My Club]", "Pointer 👉\u200b[My Club](vk.com/club123)"),
    # 9. Flag as a single emoji
    ("flag_emoji", "Country: 🇷🇺Russia", "Country: 🇷🇺\u200bRussia"),
    # 10. Family Emoji Combination
    ("family_emoji", "Family: 👩‍👩‍👧‍👦Happy", "Family: 👩‍👩‍👧‍👦\u200bHappy"),
    # 11. Real broken link
    (
        "real_broken_link",
        "👉[vk.comhttps://vk.com/@donut-android|http://vk.com/donut/dublikkk]",
        "👉\u200bvk.com/donut/dublikkk",
    ),
]


@pytest.mark.parametrize("test_id, input_text, expected_text", TEST_CASES)
def test_atomic_cases(test_id: str, input_text: str, expected_text: str) -> None:
    result = normalize_links(input_text)
    assert result == expected_text
