# app/models/notification.py
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from app.db import Base

class Notification(Base):
    """Modèle pour les notifications"""
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("sellers.id"), nullable=False, index=True)
    
    # Type de notification
    type = Column(String(50), nullable=False, index=True)  # 'facebook', 'product', 'system', 'alert'
    
    # Contenu
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    
    # Données supplémentaires (JSON)
    data = Column(JSON, default={})
    
    # État
    read = Column(Boolean, default=False, index=True)
    read_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relations
    seller = relationship("Seller", back_populates="notifications")
    
    def __repr__(self):
        return f"<Notification {self.id}: {self.title}>"
    
    @property
    def is_unread(self):
        return not self.read
    
    def mark_as_read(self):
        if not self.read:
            self.read = True
            self.read_at = datetime.utcnow()