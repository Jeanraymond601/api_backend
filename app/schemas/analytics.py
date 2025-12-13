# app/schemas/analytics.py
from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from app.schemas.product_schemas import ProductBase
from app.schemas.facebook import FacebookPostBase, FacebookCommentBase, FacebookLiveVideoBase

# Schéma pour les ventes
class SalesAnalyticsResponse(BaseModel):
    period_start: datetime
    period_end: datetime
    total_products: int = Field(..., description="Nombre total de produits")
    total_stock: int = Field(..., description="Quantité totale en stock")
    total_value: float = Field(..., description="Valeur totale du stock")
    categories: Dict[str, int] = Field(..., description="Produits par catégorie")
    products_by_day: Dict[str, int] = Field(..., description="Produits ajoutés par jour")
    top_performing: List[ProductBase] = Field(..., description="Top 5 produits performants")
    
    class Config:
        from_attributes = True

# Schéma pour Facebook
class PageAnalytics(BaseModel):
    page_name: str
    posts_count: int
    comments_count: int
    lives_count: int
    messages_count: int
    total_engagement: int
    top_posts: List[FacebookPostBase]
    recent_comments: List[FacebookCommentBase]
    active_lives: List[FacebookLiveVideoBase]

class FacebookAnalyticsResponse(BaseModel):
    period_days: int = Field(..., description="Période en jours")
    pages_analytics: Dict[str, PageAnalytics] = Field(..., description="Analytics par page")
    total_pages: int = Field(..., description="Nombre total de pages")
    overall_engagement: int = Field(..., description="Engagement total")
    
    class Config:
        from_attributes = True

# Schéma pour la performance des produits
class ProductPerformanceResponse(BaseModel):
    product_id: int
    name: str
    category: Optional[str]
    stock_quantity: Optional[int]
    price: Optional[float]
    views_count: Optional[int]
    performance_score: float = Field(..., ge=0, le=1, description="Score de performance entre 0 et 1")
    last_updated: datetime
    
    class Config:
        from_attributes = True

# Schéma pour les métriques quotidiennes
class DailyMetricsResponse(BaseModel):
    date: datetime
    new_products: int = Field(..., description="Nouveaux produits ajoutés")
    facebook_comments: int = Field(..., description="Commentaires Facebook")
    facebook_messages: int = Field(..., description="Messages Facebook")
    total_stock: int = Field(..., description="Stock total")
    total_inventory_value: float = Field(..., description="Valeur totale de l'inventaire")
    active_facebook_pages: int = Field(..., description="Pages Facebook actives")
    
    class Config:
        from_attributes = True

# Schéma pour la comparaison
class PeriodData(BaseModel):
    days: int
    products: int
    facebook_comments: int

class Differences(BaseModel):
    products: int
    products_percentage: float
    facebook_comments: int
    comments_percentage: float

class Insights(BaseModel):
    products_trend: str = Field(..., regex="^(up|down|stable)$")
    engagement_trend: str = Field(..., regex="^(up|down|stable)$")
    recommendation: str

class ComparisonResponse(BaseModel):
    period1: PeriodData
    period2: PeriodData
    differences: Differences
    insights: Insights
    
    class Config:
        from_attributes = True