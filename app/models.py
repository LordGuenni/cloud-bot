from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

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


@dataclass
class SessionState:
    session_id: str = field(default_factory=lambda: str(uuid4()))
    current_field: str = "first_name"
    values: dict[str, str] = field(default_factory=dict)
    awaiting_confirmation: bool = False
    awaiting_correction_field: bool = False

