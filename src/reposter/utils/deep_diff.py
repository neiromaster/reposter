from typing import Any

from pydantic import BaseModel

Comparable = BaseModel | dict[str, Any] | list[Any] | str | int | float | bool | None


def deep_diff(old: Comparable, new: Comparable, path: str = "") -> list[str]:
    """
    Recursively compares two objects (supports dicts, lists, Pydantic models, primitives).
    Returns a list of strings describing the changes.
    """
    changes: list[str] = []

    if isinstance(old, BaseModel) and isinstance(new, BaseModel):
        old_dict = old.model_dump()
        new_dict = new.model_dump()
        changes.extend(deep_diff(old_dict, new_dict, path))
    elif isinstance(old, dict) and isinstance(new, dict):
        all_keys = set(old.keys()) | set(new.keys())
        for key in sorted(all_keys):
            new_path = f"{path}.{key}" if path else key
            old_val = old.get(key)
            new_val = new.get(key)
            if key not in old:
                changes.append(f"➕ Добавлено: {new_path} = {repr(new_val)}")
            elif key not in new:
                changes.append(f"➖ Удалено: {new_path} (было: {repr(old_val)})")
            else:
                changes.extend(deep_diff(old_val, new_val, new_path))
    elif isinstance(old, list) and isinstance(new, list):
        max_len = max(len(old), len(new))
        for i in range(max_len):
            new_path = f"{path}[{i}]"
            if i >= len(old):
                changes.append(f"➕ Добавлено: {new_path} = {repr(new[i])}")
            elif i >= len(new):
                changes.append(f"➖ Удалено: {new_path} (было: {repr(old[i])})")
            else:
                changes.extend(deep_diff(old[i], new[i], new_path))
    elif old != new:
        changes.append(f"🔄 Изменено: {path} с {repr(old)} на {repr(new)}")

    return changes
