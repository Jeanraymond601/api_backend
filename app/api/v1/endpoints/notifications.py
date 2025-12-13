# app/api/v1/endpoints/notifications.py
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, func, or_
import logging

from app.db import get_db
from app.core.security import get_current_seller
from app.models.notification import Notification
from app.models.facebook import FacebookComment, FacebookMessage, FacebookLiveVideo
from app.schemas.notification import (
    NotificationResponse,
    NotificationListResponse,
    NotificationStatsResponse,
    NotificationSettings,
    MarkReadRequest
)

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/", response_model=NotificationListResponse)
async def get_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Récupère les notifications de l'utilisateur
    """
    try:
        query = db.query(Notification).filter(
            Notification.seller_id == current_seller.id
        )
        
        if unread_only:
            query = query.filter(Notification.read == False)
        
        total = query.count()
        notifications = query.order_by(
            desc(Notification.created_at)
        ).offset(offset).limit(limit).all()
        
        return NotificationListResponse(
            notifications=[
                NotificationResponse(
                    id=n.id,
                    type=n.type,
                    title=n.title,
                    message=n.message,
                    data=n.data,
                    read=n.read,
                    created_at=n.created_at,
                    read_at=n.read_at
                )
                for n in notifications
            ],
            total=total,
            unread_count=db.query(Notification).filter(
                Notification.seller_id == current_seller.id,
                Notification.read == False
            ).count(),
            current_page=offset // limit + 1 if limit > 0 else 1,
            total_pages=(total + limit - 1) // limit if limit > 0 else 1
        )
        
    except Exception as e:
        logger.error(f"Erreur récupération notifications: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats", response_model=NotificationStatsResponse)
async def get_notification_stats(
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Statistiques des notifications
    """
    try:
        # Total notifications
        total = db.query(Notification).filter(
            Notification.seller_id == current_seller.id
        ).count()
        
        # Non lues
        unread = db.query(Notification).filter(
            Notification.seller_id == current_seller.id,
            Notification.read == False
        ).count()
        
        # Par type
        by_type = {}
        types = db.query(Notification.type, func.count(Notification.id)).filter(
            Notification.seller_id == current_seller.id
        ).group_by(Notification.type).all()
        
        for type_name, count in types:
            by_type[type_name] = count
        
        # Aujourd'hui
        today = datetime.utcnow().date()
        today_count = db.query(Notification).filter(
            Notification.seller_id == current_seller.id,
            func.date(Notification.created_at) == today
        ).count()
        
        return NotificationStatsResponse(
            total=total,
            unread=unread,
            by_type=by_type,
            today_count=today_count,
            read_rate=(total - unread) / total * 100 if total > 0 else 0
        )
        
    except Exception as e:
        logger.error(f"Erreur stats notifications: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/mark-read")
async def mark_notifications_read(
    request: MarkReadRequest,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Marque des notifications comme lues
    """
    try:
        query = db.query(Notification).filter(
            Notification.seller_id == current_seller.id
        )
        
        if request.notification_ids:
            query = query.filter(Notification.id.in_(request.notification_ids))
        
        notifications = query.all()
        
        for notification in notifications:
            notification.read = True
            notification.read_at = datetime.utcnow()
        
        db.commit()
        
        return {
            "success": True,
            "message": f"{len(notifications)} notification(s) marquée(s) comme lue(s)",
            "count": len(notifications)
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur marquer notifications lues: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: int,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Supprime une notification
    """
    try:
        notification = db.query(Notification).filter(
            Notification.id == notification_id,
            Notification.seller_id == current_seller.id
        ).first()
        
        if not notification:
            raise HTTPException(status_code=404, detail="Notification non trouvée")
        
        db.delete(notification)
        db.commit()
        
        return {
            "success": True,
            "message": "Notification supprimée"
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur suppression notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/clear-all")
async def clear_all_notifications(
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Supprime toutes les notifications (lues)
    """
    try:
        deleted_count = db.query(Notification).filter(
            Notification.seller_id == current_seller.id,
            Notification.read == True
        ).delete()
        
        db.commit()
        
        return {
            "success": True,
            "message": f"{deleted_count} notification(s) lue(s) supprimée(s)",
            "deleted_count": deleted_count
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur suppression notifications: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/settings", response_model=NotificationSettings)
async def get_notification_settings(
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Récupère les paramètres de notifications
    """
    try:
        # Récupérer les paramètres du vendeur
        # Ici, vous pourriez avoir un modèle SellerSettings
        # Pour l'instant, retourner des valeurs par défaut
        
        return NotificationSettings(
            email_enabled=True,
            push_enabled=True,
            facebook_comments=True,
            facebook_messages=True,
            low_stock_alerts=True,
            daily_summary=True,
            quiet_hours_start=None,
            quiet_hours_end=None
        )
        
    except Exception as e:
        logger.error(f"Erreur paramètres notifications: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/settings")
async def update_notification_settings(
    settings: NotificationSettings,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Met à jour les paramètres de notifications
    """
    try:
        # Ici, vous pourriez sauvegarder dans un modèle SellerSettings
        # Pour l'instant, simuler la sauvegarde
        
        logger.info(f"Mise à jour paramètres notifications pour seller {current_seller.id}")
        
        return {
            "success": True,
            "message": "Paramètres mis à jour",
            "settings": settings
        }
        
    except Exception as e:
        logger.error(f"Erreur mise à jour paramètres: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/facebook/unread")
async def get_facebook_unread(
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Récupère les éléments Facebook non lus
    """
    try:
        # Commentaires non lus
        unread_comments = db.query(FacebookComment).filter(
            FacebookComment.seller_id == current_seller.id,
            FacebookComment.status == "new"
        ).count()
        
        # Messages non lus
        unread_messages = db.query(FacebookMessage).filter(
            FacebookMessage.sender_id != current_seller.id,  # Messages entrants seulement
            FacebookMessage.direction == "incoming",
            FacebookMessage.status.in_(["received", "delivered"])
        ).count()
        
        # Lives actifs
        active_lives = db.query(FacebookLiveVideo).filter(
            FacebookLiveVideo.seller_id == current_seller.id,
            FacebookLiveVideo.status == "live"
        ).count()
        
        return {
            "facebook_unread": {
                "comments": unread_comments,
                "messages": unread_messages,
                "active_lives": active_lives,
                "total": unread_comments + unread_messages
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erreur Facebook unread: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Fonction utilitaire pour créer des notifications
def create_notification(
    db: Session,
    seller_id: int,
    type: str,
    title: str,
    message: str,
    data: Dict = None
):
    """Crée une nouvelle notification"""
    notification = Notification(
        seller_id=seller_id,
        type=type,
        title=title,
        message=message,
        data=data or {},
        read=False,
        created_at=datetime.utcnow()
    )
    
    db.add(notification)
    db.commit()
    db.refresh(notification)
    
    logger.info(f"Notification créée: {type} pour seller {seller_id}")
    
    return notification