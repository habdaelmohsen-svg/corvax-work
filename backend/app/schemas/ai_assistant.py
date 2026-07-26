from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class AiScreenContext(BaseModel):
    module: str = Field(default="dashboard", min_length=1, max_length=80)
    screen: str = Field(default="dashboard", min_length=1, max_length=160)
    document_reference: str | None = Field(default=None, max_length=160)


class AiAssistantRequest(BaseModel):
    conversation_id: UUID | None = None
    company_id: int = Field(gt=0)
    branch_id: int | None = Field(default=None, gt=0)
    mode: Literal["help", "data", "analysis"] = "help"
    message: str = Field(min_length=1, max_length=2000)
    locale: Literal["ar", "en"] = "ar"
    screen_context: AiScreenContext = Field(default_factory=AiScreenContext)

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("message is empty")
        return normalized


class AiAssistantSource(BaseModel):
    type: Literal[
        "system-guide",
        "policy",
        "screen-context",
        "report",
        "transaction",
        "knowledge-base",
        "database",
    ]
    reference: str
    title: str
    updated_at: str | None = None


class AiAssistantResponse(BaseModel):
    conversation_id: str
    message_id: str
    answer: str
    confidence: Literal["high", "medium", "low"]
    limitations: list[str]
    sources: list[AiAssistantSource]
    tool_trace_id: str
