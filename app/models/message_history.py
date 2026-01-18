# app/models/message_history.py
from sqlalchemy import Column, Index, String, Text, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime

from app.db import Base

class MessengerMessage(Base):
    """Historique des messages Messenger"""
    
    __tablename__ = "messenger_messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Type de message
    message_type = Column(String, nullable=False)  # order_confirmation, delivery_update, etc.
    
    # Identifiants Facebook
    sender_id = Column(String, nullable=False)      # ID de l'expéditeur (page ou user)
    recipient_id = Column(String, nullable=False)   # ID du destinataire
    facebook_message_id = Column(String, unique=True)  # ID Facebook du message
    
    # Contenu
    message_content = Column(Text, nullable=False)
    quick_replies = Column(JSON)  # JSON des quick replies envoyés
    attachments = Column(JSON)    # JSON des pièces jointes
    
    # Références
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"))
    comment_id = Column(String)   # ID du commentaire Facebook source
    seller_id = Column(UUID(as_uuid=True), ForeignKey("sellers.id"))
    
    # Statut
    status = Column(String, default="sent")  # sent, delivered, read, failed
    error_message = Column(Text)
    
    # Métadonnées
    message_metadata = Column(JSON, nullable=True) # Données supplémentaires
    platform = Column(String, default="facebook_messenger")
    
    # Timestamps
    sent_at = Column(DateTime, default=datetime.utcnow)
    delivered_at = Column(DateTime)
    read_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Index
    __table_args__ = (
        Index('idx_messenger_seller', 'seller_id'),
        Index('idx_messenger_order', 'order_id'),
        Index('idx_messenger_recipient', 'recipient_id'),
        Index('idx_messenger_sent_at', 'sent_at'),
    )
    
    def __repr__(self):
        return f"<MessengerMessage {self.id} - {self.message_type}>"