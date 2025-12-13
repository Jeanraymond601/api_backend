# app/api/v1/endpoints/analytics.py
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, text
import logging

from app.db import get_db
from app.models.product import Product
from app.models.seller import Seller
from app.models.facebook import (
    FacebookPost, FacebookComment, FacebookLiveVideo, 
    FacebookMessage, FacebookPage
)
from app.core.security import get_current_seller
from app.schemas.analytics import (
    SalesAnalyticsResponse,
    FacebookAnalyticsResponse,
    ProductPerformanceResponse,
    DailyMetricsResponse,
    ComparisonResponse
)

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/sales", response_model=SalesAnalyticsResponse)
async def get_sales_analytics(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Analytics des ventes
    """
    try:
        # Par défaut: 30 derniers jours
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        # Récupérer les produits du vendeur
        products = db.query(Product).filter(
            Product.seller_id == current_seller.id,
            Product.created_at >= start_date,
            Product.created_at <= end_date
        ).all()
        
        # Calculer les métriques
        total_products = len(products)
        total_stock = sum(p.stock_quantity or 0 for p in products)
        total_value = sum((p.price or 0) * (p.stock_quantity or 0) for p in products)
        
        # Produits par catégorie
        categories = {}
        for product in products:
            category = product.category or "Non catégorisé"
            categories[category] = categories.get(category, 0) + 1
        
        return SalesAnalyticsResponse(
            period_start=start_date,
            period_end=end_date,
            total_products=total_products,
            total_stock=total_stock,
            total_value=total_value,
            categories=categories,
            products_by_day={},  # À implémenter avec des données réelles
            top_performing=products[:5] if products else []
        )
        
    except Exception as e:
        logger.error(f"Erreur analytics ventes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/facebook", response_model=FacebookAnalyticsResponse)
async def get_facebook_analytics(
    page_id: Optional[str] = Query(None),
    days_back: int = Query(30, ge=1, le=365),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Analytics Facebook
    """
    try:
        # Récupérer les pages du vendeur
        query = db.query(FacebookPage).filter(
            FacebookPage.seller_id == current_seller.id
        )
        
        if page_id:
            query = query.filter(FacebookPage.page_id == page_id)
        
        pages = query.all()
        
        if not pages:
            raise HTTPException(status_code=404, detail="Aucune page Facebook trouvée")
        
        analytics_data = {}
        
        for page in pages:
            # Posts
            posts = db.query(FacebookPost).filter(
                FacebookPost.page_id == page.id,
                FacebookPost.created_at >= datetime.utcnow() - timedelta(days=days_back)
            ).all()
            
            # Commentaires
            comments = db.query(FacebookComment).filter(
                FacebookComment.page_id == page.id,
                FacebookComment.created_at >= datetime.utcnow() - timedelta(days=days_back)
            ).all()
            
            # Lives
            lives = db.query(FacebookLiveVideo).filter(
                FacebookLiveVideo.page_id == page.page_id,
                FacebookLiveVideo.created_at >= datetime.utcnow() - timedelta(days=days_back)
            ).all()
            
            # Messages
            messages = db.query(FacebookMessage).filter(
                FacebookMessage.page_id == page.page_id,
                FacebookMessage.created_at >= datetime.utcnow() - timedelta(days=days_back)
            ).all()
            
            analytics_data[page.page_id] = {
                "page_name": page.name,
                "posts_count": len(posts),
                "comments_count": len(comments),
                "lives_count": len(lives),
                "messages_count": len(messages),
                "total_engagement": len(comments) + len(messages),
                "top_posts": sorted(posts, key=lambda x: x.likes_count or 0, reverse=True)[:5],
                "recent_comments": sorted(comments, key=lambda x: x.created_at, reverse=True)[:10],
                "active_lives": [live for live in lives if live.status == "live"]
            }
        
        return FacebookAnalyticsResponse(
            period_days=days_back,
            pages_analytics=analytics_data,
            total_pages=len(pages),
            overall_engagement=sum(data["total_engagement"] for data in analytics_data.values())
        )
        
    except Exception as e:
        logger.error(f"Erreur analytics Facebook: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/products/performance", response_model=List[ProductPerformanceResponse])
async def get_product_performance(
    limit: int = Query(20, ge=1, le=100),
    sort_by: str = Query("stock", pattern="^(stock|price|created|views)$"),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Performance des produits
    """
    try:
        query = db.query(Product).filter(
            Product.seller_id == current_seller.id
        )
        
        # Trier
        if sort_by == "stock":
            query = query.order_by(Product.stock_quantity.desc())
        elif sort_by == "price":
            query = query.order_by(Product.price.desc())
        elif sort_by == "created":
            query = query.order_by(Product.created_at.desc())
        elif sort_by == "views":
            query = query.order_by(Product.views_count.desc())
        
        products = query.limit(limit).all()
        
        performance_data = []
        for product in products:
            # Calculer le score de performance (exemple simple)
            stock_score = min((product.stock_quantity or 0) / 100, 1.0) if product.stock_quantity else 0
            price_score = 1.0 if (product.price or 0) > 0 else 0
            views_score = min((product.views_count or 0) / 1000, 1.0)
            
            performance_score = (stock_score + price_score + views_score) / 3
            
            performance_data.append(ProductPerformanceResponse(
                product_id=product.id,
                name=product.name,
                category=product.category,
                stock_quantity=product.stock_quantity,
                price=product.price,
                views_count=product.views_count,
                performance_score=round(performance_score, 3),
                last_updated=product.updated_at or product.created_at
            ))
        
        return performance_data
        
    except Exception as e:
        logger.error(f"Erreur performance produits: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/daily", response_model=DailyMetricsResponse)
async def get_daily_metrics(
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Métriques quotidiennes
    """
    try:
        today = datetime.utcnow().date()
        
        # Produits ajoutés aujourd'hui
        today_products = db.query(Product).filter(
            Product.seller_id == current_seller.id,
            func.date(Product.created_at) == today
        ).count()
        
        # Commentaires Facebook aujourd'hui
        today_comments = db.query(FacebookComment).filter(
            FacebookComment.seller_id == current_seller.id,
            func.date(FacebookComment.created_at) == today
        ).count()
        
        # Messages Facebook aujourd'hui
        today_messages = db.query(FacebookMessage).filter(
            FacebookMessage.seller_id == current_seller.id,
            func.date(FacebookMessage.created_at) == today
        ).count()
        
        # Stock total
        total_stock = db.query(func.sum(Product.stock_quantity)).filter(
            Product.seller_id == current_seller.id
        ).scalar() or 0
        
        # Valeur totale du stock
        total_value_result = db.query(
            func.sum(Product.price * Product.stock_quantity)
        ).filter(
            Product.seller_id == current_seller.id
        ).scalar()
        total_value = total_value_result or 0
        
        return DailyMetricsResponse(
            date=today,
            new_products=today_products,
            facebook_comments=today_comments,
            facebook_messages=today_messages,
            total_stock=total_stock,
            total_inventory_value=total_value,
            active_facebook_pages=db.query(FacebookPage).filter(
                FacebookPage.seller_id == current_seller.id,
                FacebookPage.is_selected == True
            ).count()
        )
        
    except Exception as e:
        logger.error(f"Erreur métriques quotidiennes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/compare", response_model=ComparisonResponse)
async def compare_periods(
    period1_days: int = Query(7, ge=1, le=365),
    period2_days: int = Query(30, ge=1, le=365),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Comparaison entre deux périodes
    """
    try:
        end_date = datetime.utcnow()
        period1_start = end_date - timedelta(days=period1_days)
        period2_start = end_date - timedelta(days=period2_days)
        
        # Période 1
        period1_products = db.query(Product).filter(
            Product.seller_id == current_seller.id,
            Product.created_at >= period1_start,
            Product.created_at <= end_date
        ).count()
        
        period1_comments = db.query(FacebookComment).filter(
            FacebookComment.seller_id == current_seller.id,
            FacebookComment.created_at >= period1_start,
            FacebookComment.created_at <= end_date
        ).count()
        
        # Période 2
        period2_products = db.query(Product).filter(
            Product.seller_id == current_seller.id,
            Product.created_at >= period2_start,
            Product.created_at <= end_date
        ).count()
        
        period2_comments = db.query(FacebookComment).filter(
            FacebookComment.seller_id == current_seller.id,
            FacebookComment.created_at >= period2_start,
            FacebookComment.created_at <= end_date
        ).count()
        
        # Calculer les différences
        product_diff = period1_products - period2_products
        comment_diff = period1_comments - period2_comments
        
        product_change = (product_diff / period2_products * 100) if period2_products > 0 else 0
        comment_change = (comment_diff / period2_comments * 100) if period2_comments > 0 else 0
        
        return ComparisonResponse(
            period1={
                "days": period1_days,
                "products": period1_products,
                "facebook_comments": period1_comments
            },
            period2={
                "days": period2_days,
                "products": period2_products,
                "facebook_comments": period2_comments
            },
            differences={
                "products": product_diff,
                "products_percentage": round(product_change, 2),
                "facebook_comments": comment_diff,
                "comments_percentage": round(comment_change, 2)
            },
            insights={
                "products_trend": "up" if product_diff > 0 else "down",
                "engagement_trend": "up" if comment_diff > 0 else "down",
                "recommendation": "Augmentez votre activité" if product_diff < 0 else "Continuez sur cette lancée"
            }
        )
        
    except Exception as e:
        logger.error(f"Erreur comparaison périodes: {e}")
        raise HTTPException(status_code=500, detail=str(e))