from __future__ import annotations

from pydantic import Field, RootModel


class State(RootModel[dict[str, dict[str, int]]]):
    root: dict[str, dict[str, int]] = Field(default_factory=dict)
