# app/api/v1/endpoints/reports.py
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, text
import logging
import json
from fastapi.responses import StreamingResponse
import csv
from io import StringIO

from app.db import get_db
from app.core.security import get_current_seller
from app.models.product import Product
from app.models.seller import Seller
from app.models.facebook import (
    FacebookPost, FacebookComment, FacebookLiveVideo, 
    FacebookMessage, FacebookPage
)
from app.schemas.reports import (
    ReportRequest,
    ReportResponse,
    ExportFormat
)

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/generate", response_model=ReportResponse)
async def generate_report(
    request: ReportRequest,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Génère un rapport personnalisé
    """
    try:
        report_data = {}
        
        # Date range
        if not request.end_date:
            request.end_date = datetime.utcnow()
        if not request.start_date:
            request.start_date = request.end_date - timedelta(days=30)
        
        # Produits
        if "products" in request.sections:
            products = db.query(Product).filter(
                Product.seller_id == current_seller.id,
                Product.created_at >= request.start_date,
                Product.created_at <= request.end_date
            ).all()
            
            report_data["products"] = {
                "total": len(products),
                "by_category": {},
                "stock_summary": {
                    "total": sum(p.stock_quantity or 0 for p in products),
                    "average": sum(p.stock_quantity or 0 for p in products) / len(products) if products else 0,
                    "min": min((p.stock_quantity or 0) for p in products) if products else 0,
                    "max": max((p.stock_quantity or 0) for p in products) if products else 0
                },
                "price_summary": {
                    "total_value": sum((p.price or 0) * (p.stock_quantity or 0) for p in products),
                    "average": sum(p.price or 0 for p in products) / len(products) if products else 0,
                    "min": min((p.price or 0) for p in products) if products else 0,
                    "max": max((p.price or 0) for p in products) if products else 0
                }
            }
            
            # Group by category
            for product in products:
                category = product.category or "Non catégorisé"
                if category not in report_data["products"]["by_category"]:
                    report_data["products"]["by_category"][category] = {
                        "count": 0,
                        "total_stock": 0,
                        "total_value": 0
                    }
                
                report_data["products"]["by_category"][category]["count"] += 1
                report_data["products"]["by_category"][category]["total_stock"] += product.stock_quantity or 0
                report_data["products"]["by_category"][category]["total_value"] += (product.price or 0) * (product.stock_quantity or 0)
        
        # Facebook
        if "facebook" in request.sections:
            pages = db.query(FacebookPage).filter(
                FacebookPage.seller_id == current_seller.id
            ).all()
            
            facebook_data = {
                "pages": [],
                "total_engagement": 0,
                "posts_summary": {},
                "comments_summary": {}
            }
            
            for page in pages:
                # Posts
                posts = db.query(FacebookPost).filter(
                    FacebookPost.page_id == page.id,
                    FacebookPost.created_at >= request.start_date,
                    FacebookPost.created_at <= request.end_date
                ).all()
                
                # Comments
                comments = db.query(FacebookComment).filter(
                    FacebookComment.page_id == page.id,
                    FacebookComment.created_at >= request.start_date,
                    FacebookComment.created_at <= request.end_date
                ).all()
                
                # Messages
                messages = db.query(FacebookMessage).filter(
                    FacebookMessage.page_id == page.page_id,
                    FacebookMessage.created_at >= request.start_date,
                    FacebookMessage.created_at <= request.end_date
                ).all()
                
                # Lives
                lives = db.query(FacebookLiveVideo).filter(
                    FacebookLiveVideo.page_id == page.page_id,
                    FacebookLiveVideo.created_at >= request.start_date,
                    FacebookLiveVideo.created_at <= request.end_date
                ).all()
                
                page_data = {
                    "page_id": page.page_id,
                    "page_name": page.name,
                    "posts": len(posts),
                    "comments": len(comments),
                    "messages": len(messages),
                    "lives": len(lives),
                    "engagement": len(comments) + len(messages),
                    "top_post": max(posts, key=lambda x: x.likes_count or 0) if posts else None
                }
                
                facebook_data["pages"].append(page_data)
                facebook_data["total_engagement"] += page_data["engagement"]
            
            report_data["facebook"] = facebook_data
        
        # Sales (à implémenter avec un vrai modèle de ventes)
        if "sales" in request.sections:
            report_data["sales"] = {
                "message": "Module de ventes à implémenter",
                "placeholder": True
            }
        
        return ReportResponse(
            report_id=f"report_{int(datetime.utcnow().timestamp())}",
            generated_at=datetime.utcnow(),
            period_start=request.start_date,
            period_end=request.end_date,
            sections=request.sections,
            data=report_data,
            summary={
                "total_products": report_data.get("products", {}).get("total", 0),
                "total_facebook_engagement": report_data.get("facebook", {}).get("total_engagement", 0),
                "pages_analyzed": len(report_data.get("facebook", {}).get("pages", [])) if "facebook" in report_data else 0
            }
        )
        
    except Exception as e:
        logger.error(f"Erreur génération rapport: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/export")
async def export_report(
    format: ExportFormat = Query(ExportFormat.JSON),
    report_type: str = Query("products", pattern="^(products|facebook|sales|all)$"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Exporte des données en différents formats
    """
    try:
        # Date range
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        data = {}
        
        if report_type in ["products", "all"]:
            products = db.query(Product).filter(
                Product.seller_id == current_seller.id,
                Product.created_at >= start_date,
                Product.created_at <= end_date
            ).all()
            
            data["products"] = [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "code_article": p.code_article,
                    "category": p.category,
                    "price": float(p.price) if p.price else 0.0,
                    "stock_quantity": p.stock_quantity or 0,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "updated_at": p.updated_at.isoformat() if p.updated_at else None
                }
                for p in products
            ]
        
        if report_type in ["facebook", "all"]:
            # Pages
            pages = db.query(FacebookPage).filter(
                FacebookPage.seller_id == current_seller.id
            ).all()
            
            data["facebook_pages"] = [
                {
                    "page_id": p.page_id,
                    "name": p.name,
                    "category": p.category,
                    "fan_count": p.fan_count,
                    "is_selected": p.is_selected,
                    "created_at": p.created_at.isoformat() if p.created_at else None
                }
                for p in pages
            ]
            
            # Comments
            comments = db.query(FacebookComment).filter(
                FacebookComment.seller_id == current_seller.id,
                FacebookComment.created_at >= start_date,
                FacebookComment.created_at <= end_date
            ).all()
            
            data["facebook_comments"] = [
                {
                    "id": c.id,
                    "message": c.message,
                    "user_name": c.user_name,
                    "post_id": c.post_id,
                    "status": c.status,
                    "intent": c.intent,
                    "sentiment": c.sentiment,
                    "created_at": c.created_at.isoformat() if c.created_at else None
                }
                for c in comments
            ]
        
        # Format de réponse
        if format == ExportFormat.JSON:
            return {
                "success": True,
                "format": "json",
                "report_type": report_type,
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                },
                "generated_at": datetime.utcnow().isoformat(),
                "data": data
            }
        
        elif format == ExportFormat.CSV:
            # Créer un CSV pour les produits
            output = StringIO()
            writer = csv.writer(output)
            
            if "products" in data:
                # En-têtes produits
                writer.writerow([
                    "ID", "Nom", "Code Article", "Catégorie", 
                    "Prix", "Stock", "Date Création", "Date Mise à Jour"
                ])
                
                # Données produits
                for product in data["products"]:
                    writer.writerow([
                        product["id"],
                        product["name"],
                        product["code_article"],
                        product["category"],
                        product["price"],
                        product["stock_quantity"],
                        product["created_at"],
                        product["updated_at"]
                    ])
            
            output.seek(0)
            filename = f"report_{report_type}_{datetime.utcnow().date()}.csv"
            
            return StreamingResponse(
                iter([output.getvalue()]),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename={filename}"
                }
            )
        
        elif format == ExportFormat.PDF:
            # Pour PDF, vous auriez besoin d'une librairie comme ReportLab
            # Ici, on retourne un message indiquant que c'est à implémenter
            return {
                "success": True,
                "message": "Export PDF à implémenter avec ReportLab",
                "format": "pdf",
                "data_available": len(data) > 0
            }
        
    except Exception as e:
        logger.error(f"Erreur export rapport: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/monthly")
async def monthly_report(
    year: int = Query(None),
    month: int = Query(None),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Rapport mensuel
    """
    try:
        # Déterminer l'année/mois
        if not year or not month:
            now = datetime.utcnow()
            year = now.year
            month = now.month
        
        # Premier et dernier jour du mois
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = datetime(year, month + 1, 1) - timedelta(days=1)
        
        # Produits du mois
        monthly_products = db.query(Product).filter(
            Product.seller_id == current_seller.id,
            Product.created_at >= start_date,
            Product.created_at <= end_date
        ).all()
        
        # Commentaires Facebook du mois
        monthly_comments = db.query(FacebookComment).filter(
            FacebookComment.seller_id == current_seller.id,
            FacebookComment.created_at >= start_date,
            FacebookComment.created_at <= end_date
        ).all()
        
        # Messages Facebook du mois
        monthly_messages = db.query(FacebookMessage).filter(
            FacebookMessage.seller_id == current_seller.id,
            FacebookMessage.created_at >= start_date,
            FacebookMessage.created_at <= end_date
        ).all()
        
        # Analyse par jour
        daily_stats = {}
        current = start_date
        while current <= end_date:
            day_str = current.strftime("%Y-%m-%d")
            
            day_products = len([p for p in monthly_products if p.created_at.date() == current.date()])
            day_comments = len([c for c in monthly_comments if c.created_at.date() == current.date()])
            day_messages = len([m for m in monthly_messages if m.created_at.date() == current.date()])
            
            daily_stats[day_str] = {
                "products": day_products,
                "comments": day_comments,
                "messages": day_messages,
            }
            
            current += timedelta(days=1)
        
        return daily_stats

    except Exception as e:
        logger.error(f"Error in get_daily_stats: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
