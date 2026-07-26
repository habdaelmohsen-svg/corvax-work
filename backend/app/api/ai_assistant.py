from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas.ai_assistant import AiAssistantRequest, AiAssistantResponse
from app.services.ai_assistant_service import answer_ai_assistant

router = APIRouter(prefix="/ai-assistant", tags=["AI Assistant"])


@router.post("/messages", response_model=AiAssistantResponse)
def create_message(
    payload: AiAssistantRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiAssistantResponse:
    return answer_ai_assistant(db, current_user, payload)
