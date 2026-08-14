from sqlalchemy import select
from typing import List
from app.repositories.base_repository import BaseRepository
from app.models.ai_chat import ChatSession, ChatMessage
import uuid

class ChatRepository(BaseRepository[ChatSession]):
    def __init__(self, db_session=None):
        super().__init__(model_class=ChatSession, db_session=db_session)


    async def get_session_history(self, session_id: uuid.UUID) -> List[ChatMessage]:
        stmt = select(ChatMessage).where(
            ChatMessage.session_id == session_id,
            ChatMessage.is_deleted == False
        ).order_by(ChatMessage.created_at.asc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def save_message(self, session_id: uuid.UUID, sender_type: str, content: str, metadata: dict = None) -> ChatMessage:
        msg = ChatMessage(session_id=session_id, sender_type=sender_type, content=content, metadata_json=metadata)
        self.db.add(msg)
        await self.db.commit()
        await self.db.refresh(msg)
        return msg
