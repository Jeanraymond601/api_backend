# app/models/order.py
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime
from app.db import Base

class Order(Base):
    """Modèle pour les commandes"""
    __tablename__ = "orders"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    order_number = Column(String(50), unique=True, nullable=False, index=True)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("sellers.id"), nullable=False, index=True)
    
    # Informations client
    customer_name = Column(String(200), nullable=False)
    customer_phone = Column(String(20), nullable=False)
    shipping_address = Column(Text)
    needs_delivery = Column(Boolean, default=True)
    
    # Informations commande
    total_amount = Column(Numeric(10, 2), nullable=False, default=0)
    status = Column(String(20), nullable=False, default="pending")
    source = Column(String(50), default="facebook_comment")  # facebook_comment, manual, etc.
    source_id = Column(String(100))  # ID du commentaire Facebook ou autre
    
    # Métadonnées
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relations
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Order {self.order_number} - {self.customer_name}>"

class OrderItem(Base):
    """Modèle pour les items de commande"""
    __tablename__ = "order_items"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=True)  # Peut être null si produit supprimé
    product_name = Column(String(255), nullable=False)
    product_code = Column(String(100), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    total_price = Column(Numeric(10, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    
    # Relations
    order = relationship("Order", back_populates="items")
    
    def __repr__(self):
        return f"<OrderItem {self.product_code} x{self.quantity}>"