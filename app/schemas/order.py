# app/schemas/order.py
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from enum import Enum

class OrderStatus(str, Enum):
    PENDING = "pending"
    PREPARING = "preparing"
    DELIVERING = "delivering"
    DONE = "done"
    CANCELLED = "cancelled"

class OrderSource(str, Enum):
    FACEBOOK_COMMENT = "facebook_comment"
    MANUAL = "manual"
    WEBSITE = "website"
    MESSENGER = "messenger"

# ============ REQUEST SCHEMAS ============

class OrderItemCreate(BaseModel):
    """Schéma pour créer un item de commande"""
    product_id: Optional[UUID] = None  # Peut être null
    product_name: str
    product_code: str
    quantity: int = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)
    
    class Config:
        from_attributes = True

class OrderCreate(BaseModel):
    """Schéma pour créer une commande"""
    customer_name: str = Field(..., min_length=2, max_length=200)
    customer_phone: str = Field(..., min_length=8, max_length=20)
    shipping_address: Optional[str] = None
    needs_delivery: bool = True
    items: List[OrderItemCreate] = Field(..., min_items=1)
    source: OrderSource = OrderSource.FACEBOOK_COMMENT
    source_id: Optional[str] = None  # ID du commentaire Facebook
    metadata: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True

class OrderUpdate(BaseModel):
    """Schéma pour mettre à jour une commande"""
    status: Optional[OrderStatus] = None
    customer_name: Optional[str] = Field(None, min_length=2, max_length=200)
    customer_phone: Optional[str] = Field(None, min_length=8, max_length=20)
    shipping_address: Optional[str] = None
    needs_delivery: Optional[bool] = None
    
    class Config:
        from_attributes = True

class OrderFilter(BaseModel):
    """Schéma pour filtrer les commandes"""
    status: Optional[OrderStatus] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    needs_delivery: Optional[bool] = None
    source: Optional[OrderSource] = None
    
    class Config:
        from_attributes = True

# ============ RESPONSE SCHEMAS ============

class OrderItemResponse(BaseModel):
    """Schéma pour la réponse d'un item de commande"""
    id: UUID
    product_id: Optional[UUID]
    product_name: str
    product_code: str
    quantity: int
    unit_price: float
    total_price: float
    created_at: datetime
    
    class Config:
        from_attributes = True

class OrderResponse(BaseModel):
    """Schéma pour la réponse d'une commande"""
    id: UUID
    order_number: str
    seller_id: UUID
    customer_name: str
    customer_phone: str
    shipping_address: Optional[str]
    needs_delivery: bool
    total_amount: float
    status: OrderStatus
    source: OrderSource
    source_id: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    items: List[OrderItemResponse]
    
    class Config:
        from_attributes = True

class OrderListResponse(BaseModel):
    """Schéma pour la réponse d'une liste de commandes"""
    success: bool = True
    count: int
    total: int
    orders: List[OrderResponse]
    
    class Config:
        from_attributes = True

class OrderStatsResponse(BaseModel):
    """Schéma pour les statistiques de commandes"""
    total_orders: int
    total_amount: float
    pending_orders: int
    preparing_orders: int
    delivering_orders: int
    completed_orders: int
    cancelled_orders: int
    average_order_value: float
    orders_by_source: Dict[str, int]
    
    class Config:
        from_attributes = True

# ============ MESSENGER CONFIRMATION SCHEMAS ============

class MessengerConfirmationRequest(BaseModel):
    """Schéma pour la confirmation via Messenger"""
    order_id: UUID
    page_id: str
    customer_facebook_id: str
    confirmed_details: Dict[str, Any]  # Détails confirmés par le client
    
    class Config:
        from_attributes = True

class OrderConfirmationResponse(BaseModel):
    """Schéma pour la réponse de confirmation"""
    success: bool
    order_id: UUID
    order_number: str
    confirmed_at: datetime
    next_steps: str
    
    class Config:
        from_attributes = True