from sqlalchemy import Column, String, DateTime, Integer, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.db import Base

class PasswordResetCode(Base):
    __tablename__ = "password_reset_codes"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # Référence à l'user
    email = Column(String(255), nullable=False, index=True)  # Email de l'utilisateur
    code = Column(String(6), nullable=False)  # Code à 6 chiffres
    reset_token = Column(String(255), nullable=True, unique=True, index=True)  # Token après validation
    attempts = Column(Integer, default=0)  # Nombre de tentatives échouées
    verified = Column(Boolean, default=False)  # Si le code est vérifié
    expires_at = Column(DateTime, nullable=False)  # Date d'expiration (15 minutes)
    created_at = Column(DateTime, server_default=func.now())  # Date de création
    used_at = Column(DateTime, nullable=True)  # Quand le code est utilisé
    
    def __repr__(self):
        return f"<PasswordResetCode(email='{self.email}', code='{self.code}', expires_at='{self.expires_at}')>"
    
    def is_expired(self):
        from datetime import datetime
        return datetime.now() > self.expires_at
    
    def is_usable(self):
        return not self.used_at and not self.is_expired() and self.attempts < 3