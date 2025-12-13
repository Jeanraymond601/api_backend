from sqlalchemy import Column, String, Text, TIMESTAMP, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db import Base
import uuid
from datetime import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name = Column(Text, nullable=False)
    email = Column(Text, unique=True, nullable=False)
    telephone = Column(Text)
    adresse = Column(Text)
    role = Column(Text, nullable=False)  # 'ADMIN', 'VENDEUR', 'LIVREUR', 'client'
    statut = Column(Text, default="en_attente")  # 'en_attente', 'actif', 'suspendu', 'rejeté'
    password = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, default=datetime.now)
    updated_at = Column(TIMESTAMP, default=datetime.now, onupdate=datetime.now)
    is_active = Column(Boolean, default=True)
    
    # Relation avec Seller (si c'est un vendeur)
    seller = relationship("Seller", back_populates="user", uselist=False, cascade="all, delete-orphan")
    
    # Relations pour le système livreurs - SIMPLIFIÉES
    # Enlever les relations complexes pour le moment
    
    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"