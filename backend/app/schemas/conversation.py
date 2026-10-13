from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.chat_log import ChatLogOut


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    updated_at: datetime


class ConversationDetailOut(ConversationOut):
    messages: list[ChatLogOut]
