from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StartSessionResponse(BaseModel):
    session_id: str
    reply: str
    expected_field: str


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    expected_field: str | None
    completed: bool = False
    account: dict[str, Any] | None = None


class UserProfile:
    def __init__(self) -> None:
        self.first_name: str | None = None
        self.last_name: str | None = None
        self.birthdate: str | None = None
        self.email: str | None = None
        self.phone: str | None = None
        self.street: str | None = None
        self.house_number: str | None = None
        self.postal_code: str | None = None
        self.city: str | None = None
        self.country: str | None = None
        self.confirmed: bool = False
