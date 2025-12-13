# E:\Live_commerce\backends\app\models\seller.py - VERSION SIMPLIFIÉE

from sqlalchemy import Column, Text, TIMESTAMP, Date, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db import Base
import uuid
from datetime import datetime

class Seller(Base):
    __tablename__ = "sellers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, unique=True)
    company_name = Column(Text, nullable=False)
    facebook_page = Column(Text)
    page_access_token = Column(Text)
    abonnement_type = Column(Text, default="gratuit")
    abonnement_status = Column(Text, default="actif")
    date_debut_abonnement = Column(Date, default=datetime.now().date)
    date_fin_abonnement = Column(Date, default=datetime.now().date)
    created_at = Column(TIMESTAMP, default=datetime.now)
    updated_at = Column(TIMESTAMP, default=datetime.now, onupdate=datetime.now)
    
    # ✅ CORRECTION: Relations SIMPLIFIÉES
    user = relationship("User", back_populates="seller")
    notifications = relationship("Notification", back_populates="seller", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Seller(id={self.id}, company_name={self.company_name})>"