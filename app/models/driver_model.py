from sqlalchemy import Column, String, Boolean, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db import Base
import uuid
from datetime import datetime

class Driver(Base):
    __tablename__ = "drivers"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    zone_livraison = Column(String(255))
    disponibilite = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relations
    user = relationship("User", foreign_keys=[user_id], backref="driver_profile")
    seller_user = relationship("User", foreign_keys=[seller_id], backref="sellers_drivers")
    
    def __repr__(self):
        return f"<Driver(id={self.id}, user_id={self.user_id}, seller_id={self.seller_id})>"