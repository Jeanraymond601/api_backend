# E:\Live_commerce\backends\app\schemas\product_schemas.py

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

# ==================== BASE SCHEMAS ====================

class ProductBase(BaseModel):
    """Schéma de base pour les produits"""
    name: str = Field(..., min_length=1, max_length=255)
    category_name: str = Field(..., min_length=1, max_length=150)
    description: Optional[str] = None
    color: Optional[str] = Field(None, max_length=100)
    size: Optional[str] = Field(None, max_length=50)
    price: float = Field(..., gt=0, le=10000000)
    stock: int = Field(default=0, ge=0)
    is_active: bool = Field(default=True)
    
    @validator('name')
    def name_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Le nom du produit ne peut pas être vide")
        return v.strip()
    
    @validator('category_name')
    def category_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("La catégorie ne peut pas être vide")
        return v.strip().title()
    
    @validator('price')
    def price_valid(cls, v):
        if v <= 0:
            raise ValueError("Le prix doit être supérieur à 0")
        return round(v, 2)

# ==================== CREATE SCHEMA ====================

class ProductCreate(ProductBase):
    """Schéma pour la création d'un produit"""
    seller_id: Optional[UUID] = None  # Sera rempli automatiquement

# ==================== UPDATE SCHEMA ====================

class ProductUpdate(BaseModel):
    """Schéma pour la mise à jour d'un produit"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    category_name: Optional[str] = Field(None, min_length=1, max_length=150)
    description: Optional[str] = None
    color: Optional[str] = Field(None, max_length=100)
    size: Optional[str] = Field(None, max_length=50)
    price: Optional[float] = Field(None, gt=0, le=10000000)
    stock: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None
    
    class Config:
        extra = "forbid"

# ==================== RESPONSE SCHEMAS ====================

class ProductResponse(BaseModel):
    """Schéma de réponse pour un produit"""
    id: UUID
    seller_id: UUID
    name: str
    category_name: str
    description: Optional[str]
    code_article: str
    color: Optional[str]
    size: Optional[str]
    price: float
    stock: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class ProductListResponse(BaseModel):
    """Schéma pour la liste paginée des produits"""
    items: List[ProductResponse]
    total: int
    page: int
    size: int
    pages: int

# ==================== FILTER SCHEMA ====================

class ProductFilter(BaseModel):
    """Schéma pour le filtrage des produits"""
    seller_id: Optional[UUID] = None
    category_name: Optional[str] = None
    is_active: Optional[bool] = None
    price_min: Optional[float] = Field(None, ge=0)
    price_max: Optional[float] = Field(None, ge=0)
    search: Optional[str] = None
    
    @validator('price_max')
    def validate_price_range(cls, v, values):
        if v and 'price_min' in values and values['price_min']:
            if v < values['price_min']:
                raise ValueError("price_max doit être supérieur ou égal à price_min")
        return v

# ==================== CODE GENERATION ====================

class CodeGenerationRequest(BaseModel):
    """Requête pour tester la génération de code"""
    category_name: str
    seller_id: UUID

class CodeGenerationResponse(BaseModel):
    """Réponse pour la génération de code"""
    category_name: str
    seller_id: UUID
    generated_code: str
    next_number: int

# ==================== STATISTICS SCHEMA ====================

class ProductStats(BaseModel):
    """Statistiques des produits"""
    total_products: int
    active_products: int
    categories_count: int
    total_stock: int
    total_value: float