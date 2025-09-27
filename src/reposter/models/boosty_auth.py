from __future__ import annotations

from pydantic import BaseModel


class BoostyAuthData(BaseModel):
    """Model for Boosty authentication data."""

    access_token: str
    refresh_token: str
    device_id: str
    expires_in: int
