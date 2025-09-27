from src.reposter.models import Post
from src.reposter.utils.deep_diff import deep_diff


class TestDeepDiff:
    def test_deep_diff_same_primitives(self):
        """Test deep diff with same primitive values."""
        old = 5
        new = 5
        result = deep_diff(old, new)
        assert result == []

    def test_deep_diff_different_primitives(self):
        """Test deep diff with different primitive values."""
        old = 5
        new = 10
        result = deep_diff(old, new)
        assert result == ["🔄 Изменено:  с 5 на 10"]

    def test_deep_diff_string_change(self):
        """Test deep diff with different strings."""
        old = "hello"
        new = "world"
        result = deep_diff(old, new)
        assert result == ["🔄 Изменено:  с 'hello' на 'world'"]

    def test_deep_diff_none_values(self):
        """Test deep diff with None values."""
        old = None
        new = "value"
        result = deep_diff(old, new)
        assert result == ["🔄 Изменено:  с None на 'value'"]

    def test_deep_diff_list_addition(self):
        """Test deep diff with list addition."""
        old = [1, 2]
        new = [1, 2, 3]
        result = deep_diff(old, new)
        assert result == ["➕ Добавлено: [2] = 3"]

    def test_deep_diff_list_deletion(self):
        """Test deep diff with list deletion."""
        old = [1, 2, 3]
        new = [1, 2]
        result = deep_diff(old, new)
        assert result == ["➖ Удалено: [2] (было: 3)"]

    def test_deep_diff_list_modification(self):
        """Test deep diff with list modification."""
        old = [1, 2, 3]
        new = [1, 4, 3]
        result = deep_diff(old, new)
        assert result == ["🔄 Изменено: [1] с 2 на 4"]

    def test_deep_diff_nested_list(self):
        """Test deep diff with nested lists."""
        old = [[1, 2], [3, 4]]
        new = [[1, 5], [3, 4]]
        result = deep_diff(old, new)
        assert result == ["🔄 Изменено: [0][1] с 2 на 5"]

    def test_deep_diff_dict_addition(self):
        """Test deep diff with dictionary addition."""
        old = {"a": 1}
        new = {"a": 1, "b": 2}
        result = deep_diff(old, new)
        assert result == ["➕ Добавлено: b = 2"]

    def test_deep_diff_dict_deletion(self):
        """Test deep diff with dictionary deletion."""
        old = {"a": 1, "b": 2}
        new = {"a": 1}
        result = deep_diff(old, new)
        assert result == ["➖ Удалено: b (было: 2)"]

    def test_deep_diff_dict_modification(self):
        """Test deep diff with dictionary modification."""
        old = {"a": 1, "b": 2}
        new = {"a": 3, "b": 2}
        result = deep_diff(old, new)
        assert result == ["🔄 Изменено: a с 1 на 3"]

    def test_deep_diff_nested_dict(self):
        """Test deep diff with nested dictionaries."""
        old = {"a": {"x": 1, "y": 2}}
        new = {"a": {"x": 3, "y": 2}}
        result = deep_diff(old, new)
        assert result == ["🔄 Изменено: a.x с 1 на 3"]

    def test_deep_diff_complex_nested_structure(self):
        """Test deep diff with complex nested structure."""
        old = {"user": {"name": "John", "settings": {"theme": "dark", "notifications": True}}, "posts": [1, 2, 3]}
        new = {"user": {"name": "Jane", "settings": {"theme": "light", "notifications": True}}, "posts": [1, 2, 4]}
        result = deep_diff(old, new)
        expected = [
            "🔄 Изменено: user.name с 'John' на 'Jane'",
            "🔄 Изменено: user.settings.theme с 'dark' на 'light'",
            "🔄 Изменено: posts[2] с 3 на 4",
        ]
        assert sorted(result) == sorted(expected)

    def test_deep_diff_list_expansion(self):
        """Test deep diff when a list grows."""
        old = [1]
        new = [1, 2, 3]
        result = deep_diff(old, new)
        assert result == ["➕ Добавлено: [1] = 2", "➕ Добавлено: [2] = 3"]

    def test_deep_diff_empty_to_filled_dict(self):
        """Test deep diff from empty to filled dict."""
        old: dict[str, str] = {}
        new = {"key": "value"}
        result = deep_diff(old, new)
        assert result == ["➕ Добавлено: key = 'value'"]

    def test_deep_diff_pydantic_models(self):
        """Test deep diff with Pydantic models."""
        # Create two posts that are different
        old_post = Post(id=1, text="old", date=1000, attachments=[], owner_id=1, from_id=1, is_pinned=None)
        new_post = Post(id=1, text="new", date=1000, attachments=[], owner_id=1, from_id=1, is_pinned=None)

        result = deep_diff(old_post, new_post)
        # This should show that the text changed
        assert any("text" in item and "old" in item and "new" in item for item in result)

    def test_deep_diff_mixed_types(self):
        """Test deep diff with mixed types."""
        old = {"value": 42}
        new = {"value": "42"}
        result = deep_diff(old, new)
        assert result == ["🔄 Изменено: value с 42 на '42'"]
