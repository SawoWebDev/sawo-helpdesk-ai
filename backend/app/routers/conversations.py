from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_owner_hash
from app.db.session import get_db
from app.models.chat_log import ChatLog
from app.models.conversation import Conversation
from app.schemas.conversation import ConversationDetailOut, ConversationOut

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

# "Your Recent Conversations" is a sidebar, not an archive — cap how many are
# ever listed. Older conversations are never deleted, just not shown here.
CONVERSATION_LIST_LIMIT = 50


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    owner_hash: str = Depends(get_owner_hash),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.owner_hash == owner_hash)
        .order_by(Conversation.updated_at.desc())
        .limit(CONVERSATION_LIST_LIMIT)
    )
    return result.scalars().all()


@router.get("/{conversation_id}", response_model=ConversationDetailOut)
async def get_conversation(
    conversation_id: int,
    owner_hash: str = Depends(get_owner_hash),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    conversation = result.scalar_one_or_none()
    # Same 404 whether the conversation doesn't exist or belongs to someone
    # else, so a conversation_id can't be probed to learn which is true.
    if conversation is None or conversation.owner_hash != owner_hash:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    messages_result = await db.execute(
        select(ChatLog).where(ChatLog.conversation_id == conversation_id).order_by(ChatLog.created_at.asc())
    )
    return ConversationDetailOut(
        id=conversation.id,
        title=conversation.title,
        updated_at=conversation.updated_at,
        messages=list(messages_result.scalars().all()),
    )
