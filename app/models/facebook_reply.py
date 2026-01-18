# app/models/facebook_reply.py
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime

from app.db import Base

class FacebookReplyHistory(Base):
    """Historique des réponses Facebook automatiques"""
    
    __tablename__ = "facebook_reply_history"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    comment_id = Column(String, nullable=False, index=True)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    message = Column(Text, nullable=False)
    facebook_response_id = Column(String)  # ID de la réponse sur Facebook
    sent_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<FacebookReplyHistory {self.comment_id}>"