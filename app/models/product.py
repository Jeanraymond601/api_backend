# E:\Live_commerce\backends\app\models\product.py - VERSION SIMPLIFIÉE

from sqlalchemy import Column, String, Integer, Numeric, Boolean, DateTime, Text, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.db import Base

class Product(Base):
    """Modèle SQLAlchemy pour les produits"""
    
    __tablename__ = "products"
    
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        nullable=False
    )
    seller_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True
        # Note: Pas de ForeignKey vers sellers.id car pas nécessaire
    )
    name = Column(String(255), nullable=False)
    category_name = Column(String(150), nullable=False, index=True)
    description = Column(Text)
    code_article = Column(String(100), nullable=False, index=True)
    color = Column(String(100))
    size = Column(String(50))
    price = Column(Numeric(10, 2), nullable=False)
    stock = Column(Integer, default=0)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # ✅ ENLEVER la relation vers Seller si elle existe
    # seller = relationship("Seller", back_populates="products")
    
    # Définir les contraintes de table
    __table_args__ = (
        # Contrainte d'unicité seller_id + code_article
        Index('uq_product_seller_code', 'seller_id', 'code_article', unique=True),
        
        # Contraintes de validation
        CheckConstraint('price >= 0', name='products_price_check'),
        CheckConstraint('stock >= 0', name='products_stock_check'),
    )
    
    def __repr__(self):
        return f"<Product {self.code_article}: {self.name}>"