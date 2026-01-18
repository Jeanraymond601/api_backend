# app/api/v1/endpoints/facebook_messenger.py - VERSION COMPLÈTE CORRIGÉE
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
import uuid
from typing import Dict, Any
import logging
import aiohttp
import traceback

from app.db import get_db
from app.core.dependencies import get_current_seller
from app.services.facebook_messenger_service import FacebookMessengerService
from app.core.config import settings

# Configuration du logger
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/facebook/messenger", tags=["facebook-messenger"])

# ================================
# FONCTIONS AUXILIAIRES
# ================================

def extract_seller_id(current_seller):
    """Extrait l'ID du vendeur de l'objet/dictionnaire current_seller"""
    try:
        # Si c'est un dictionnaire
        if isinstance(current_seller, dict):
            seller_id = current_seller.get('seller_id') or \
                       current_seller.get('id') or \
                       current_seller.get('user_id')
            
            if seller_id:
                return uuid.UUID(seller_id) if isinstance(seller_id, str) else seller_id
        
        # Si c'est un objet avec attribut id
        elif hasattr(current_seller, 'id'):
            return current_seller.id
        
        # Si c'est un objet avec attribut seller_id
        elif hasattr(current_seller, 'seller_id'):
            return current_seller.seller_id
        
        # Fallback
        return uuid.UUID("53ee0b71-dc52-448c-b265-e4b776dbbab2")
            
    except Exception as e:
        logger.error(f"Erreur extraction seller_id: {e}")
        return uuid.UUID("53ee0b71-dc52-448c-b265-e4b776dbbab2")


async def get_facebook_token_from_db(seller_id: uuid.UUID, db: Session):
    """Récupère le token Facebook depuis la base (comme l'auto-reply)"""
    try:
        from app.models.facebook import FacebookPage
        
        # Rechercher la page sélectionnée du vendeur
        page = db.query(FacebookPage).filter(
            FacebookPage.seller_id == seller_id,
            FacebookPage.is_selected == True
        ).first()
        
        if page and page.page_access_token:
            logger.info(f"Token trouvé pour seller {seller_id}: {page.page_access_token[:30]}...")
            return page.page_access_token
        
        # Si pas de page sélectionnée, prendre la première
        if not page:
            page = db.query(FacebookPage).filter(
                FacebookPage.seller_id == seller_id
            ).first()
            
            if page and page.page_access_token:
                logger.info(f"Token trouvé (première page) pour seller {seller_id}: {page.page_access_token[:30]}...")
                return page.page_access_token
        
        logger.warning(f"Aucun token trouvé pour seller {seller_id}")
        return None
        
    except Exception as e:
        logger.error(f"Erreur récupération token: {e}")
        return None


async def verify_facebook_token(token: str):
    """Vérifie si un token Facebook est valide"""
    try:
        url = f"https://graph.facebook.com/{settings.FACEBOOK_API_VERSION}/me"
        params = {
            "access_token": token,
            "fields": "id,name"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return {"valid": True, "page_info": data}
                else:
                    error_text = await response.text()
                    logger.error(f"Token invalide: {response.status} - {error_text}")
                    return {"valid": False, "error": f"HTTP {response.status}: {error_text}"}
                    
    except Exception as e:
        logger.error(f"Erreur vérification token: {e}")
        return {"valid": False, "error": str(e)}


# ================================
# ENDPOINTS
# ================================

@router.post("/process-comment/{comment_id}")
async def process_comment_with_messenger(
    comment_id: str,
    background_tasks: BackgroundTasks,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Traite un commentaire et envoie message Messenger + réponse publique
    """
    try:
        # Extraire l'ID du vendeur
        seller_id = extract_seller_id(current_seller)
        logger.info(f"Processing comment {comment_id} for seller {seller_id}")
        
        # Récupérer le token Facebook
        token = await get_facebook_token_from_db(seller_id, db)
        
        if not token:
            return {
                "success": False,
                "error": "Token Facebook non trouvé",
                "message": "Veuillez d'abord configurer l'intégration Facebook",
                "seller_id": str(seller_id),
                "next_steps": [
                    "1. Aller sur /api/v1/facebook/login",
                    "2. Connecter votre compte Facebook",
                    "3. Sélectionner votre page",
                    "4. Autoriser les permissions"
                ]
            }
        
        # Vérifier si le token est valide
        verification = await verify_facebook_token(token)
        if not verification["valid"]:
            return {
                "success": False,
                "error": f"Token invalide: {verification.get('error', 'Unknown error')}",
                "seller_id": str(seller_id)
            }
        
        page_info = verification.get("page_info", {})
        
        # Récupérer le nom de la page depuis la base de données
        from app.models.facebook import FacebookPage
        db_page = db.query(FacebookPage).filter(
            FacebookPage.seller_id == seller_id,
            FacebookPage.is_selected == True
        ).first()
        
        db_page_name = "Unknown"
        if db_page:
            db_page_name = db_page.name
        
        # Lancer le processus en arrière-plan
        messenger_service = FacebookMessengerService(db)
        
        background_tasks.add_task(
            messenger_service.process_comment_and_send_message,
            comment_id=comment_id,
            seller_id=seller_id
        )
        
        return {
            "success": True,
            "message": "Traitement du commentaire lancé en arrière-plan",
            "comment_id": comment_id,
            "seller_id": str(seller_id),
            "has_token": True,
            "token_preview": token[:30] + "...",
            "page_id": page_info.get('id', "unknown"),
            "page_name": db_page_name,
            "note": "Les messages seront envoyés dans quelques secondes"
        }
        
    except Exception as e:
        logger.error(f"Erreur process_comment_with_messenger: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/check-token")
async def check_messenger_token(
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Vérifie l'état du token Messenger"""
    try:
        # Extraire l'ID du vendeur
        seller_id = extract_seller_id(current_seller)
        
        # Récupérer le token
        token = await get_facebook_token_from_db(seller_id, db)
        
        has_token = bool(token)
        permissions_ok = False
        page_info = {}
        token_valid = False
        
        if token:
            # Vérifier si le token est valide
            verification = await verify_facebook_token(token)
            token_valid = verification["valid"]
            page_info = verification.get("page_info", {})
            
            if token_valid:
                # Vérifier les permissions Messenger
                try:
                    messenger_service = FacebookMessengerService(db)
                    permissions_ok = await messenger_service._check_messenger_permissions(token)
                except Exception as e:
                    logger.error(f"Erreur vérification permissions: {e}")
                    permissions_ok = False
        
        # Récupérer les infos de la page depuis la DB
        from app.models.facebook import FacebookPage
        page = db.query(FacebookPage).filter(
            FacebookPage.seller_id == seller_id,
            FacebookPage.is_selected == True
        ).first()
        
        page_data = {}
        if page:
            page_data = {
                "name": page.name,
                "page_id": page.page_id,
                "is_selected": page.is_selected,
                "auto_reply_enabled": page.auto_reply_enabled
            }
        
        return {
            "success": True,
            "has_token": has_token,
            "token_valid": token_valid,
            "permissions_ok": permissions_ok,
            "token_preview": token[:30] + "..." if token else None,
            "token_length": len(token) if token else 0,
            "page": page_data,
            "graph_api_info": page_info if token_valid else {},
            "seller_id": str(seller_id),
            "status": "READY" if (has_token and token_valid and permissions_ok) else "NOT_CONFIGURED",
            "requirements": [
                "pages_messaging",
                "pages_manage_metadata"
            ]
        }
        
    except Exception as e:
        logger.error(f"Erreur check_messenger_token: {e}")
        return {
            "success": False,
            "error": str(e),
            "seller_id": str(seller_id) if 'seller_id' in locals() else "unknown"
        }


@router.post("/send-confirmation/{order_id}")
async def send_order_confirmation_messenger(
    order_id: uuid.UUID,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Envoie un message de confirmation Messenger pour une commande"""
    try:
        from app.models.order import Order
        from app.models.facebook import FacebookComment
        
        # Extraire l'ID du vendeur
        seller_id = extract_seller_id(current_seller)
        
        # Récupérer la commande
        order = db.query(Order).filter(
            Order.id == order_id,
            Order.seller_id == seller_id
        ).first()
        
        if not order:
            raise HTTPException(status_code=404, detail="Commande non trouvée")
        
        # Récupérer le commentaire associé
        comment = db.query(FacebookComment).filter(
            FacebookComment.id == order.source_id
        ).first()
        
        if not comment:
            return {
                "success": False,
                "error": "Commentaire source non trouvé",
                "order_id": str(order_id)
            }
        
        # Récupérer le token
        token = await get_facebook_token_from_db(seller_id, db)
        if not token:
            raise HTTPException(status_code=400, detail="Token Messenger non disponible")
        
        # Vérifier le token
        verification = await verify_facebook_token(token)
        if not verification["valid"]:
            raise HTTPException(status_code=400, detail=f"Token invalide: {verification.get('error')}")
        
        # Envoyer le message
        messenger_service = FacebookMessengerService(db)
        result = await messenger_service.send_order_confirmation_message(
            order=order,
            comment=comment,
            seller_id=seller_id
        )
        
        if result["success"]:
            return {
                "success": True,
                "message": "Message de confirmation envoyé",
                "messenger_result": result,
                "order_number": order.order_number,
                "customer_name": order.customer_name
            }
        else:
            raise HTTPException(status_code=400, detail=result.get("error"))
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur send_order_confirmation_messenger: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/request-address/{order_id}")
async def request_delivery_address(
    order_id: uuid.UUID,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Demande l'adresse de livraison via Messenger"""
    try:
        from app.models.order import Order
        
        # Extraire l'ID du vendeur
        seller_id = extract_seller_id(current_seller)
        
        order = db.query(Order).filter(
            Order.id == order_id,
            Order.seller_id == seller_id
        ).first()
        
        if not order:
            raise HTTPException(status_code=404, detail="Commande non trouvée")
        
        # Récupérer l'ID Facebook du client
        from app.models.facebook import FacebookComment
        comment = db.query(FacebookComment).filter(
            FacebookComment.id == order.source_id
        ).first()
        
        if not comment or not comment.user_id:
            return {
                "success": False,
                "error": "ID Facebook du client non disponible"
            }
        
        # Récupérer le token
        token = await get_facebook_token_from_db(seller_id, db)
        if not token:
            raise HTTPException(status_code=400, detail="Token Messenger non disponible")
        
        # Vérifier le token
        verification = await verify_facebook_token(token)
        if not verification["valid"]:
            raise HTTPException(status_code=400, detail=f"Token invalide: {verification.get('error')}")
        
        # Envoyer la demande d'adresse
        messenger_service = FacebookMessengerService(db)
        result = await messenger_service.send_delivery_address_request(
            recipient_id=comment.user_id,
            customer_name=order.customer_name,
            order_number=order.order_number,
            page_access_token=token
        )
        
        if result["success"]:
            return {
                "success": True,
                "message": "Demande d'adresse envoyée",
                "messenger_result": result
            }
        else:
            raise HTTPException(status_code=400, detail=result.get("error"))
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur request_delivery_address: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/message-history/{order_id}")
async def get_messenger_history(
    order_id: uuid.UUID,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Récupère l'historique des messages pour une commande"""
    try:
        # Extraire l'ID du vendeur
        seller_id = extract_seller_id(current_seller)
        
        from app.models.message_history import MessengerMessage
        
        messages = db.query(MessengerMessage).filter(
            MessengerMessage.order_id == order_id,
            MessengerMessage.seller_id == seller_id
        ).order_by(MessengerMessage.sent_at.desc()).all()
        
        return {
            "success": True,
            "order_id": str(order_id),
            "total_messages": len(messages),
            "messages": [
                {
                    "id": str(msg.id),
                    "type": msg.message_type,
                    "sender": msg.sender_id,
                    "recipient": msg.recipient_id,
                    "content": msg.message_content[:200] + "..." if len(msg.message_content) > 200 else msg.message_content,
                    "status": msg.status,
                    "sent_at": msg.sent_at.isoformat() if msg.sent_at else None,
                    "facebook_message_id": msg.facebook_message_id
                }
                for msg in messages
            ]
        }
        
    except Exception as e:
        logger.error(f"Erreur get_messenger_history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/seller-info")
async def debug_seller_info(
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Endpoint de debug pour voir ce que retourne get_current_seller"""
    try:
        seller_id = extract_seller_id(current_seller)
        
        return {
            "success": True,
            "seller_id": str(seller_id),
            "type": str(type(current_seller)),
            "is_dict": isinstance(current_seller, dict),
            "keys": list(current_seller.keys()) if isinstance(current_seller, dict) else None,
            "has_seller_id_key": 'seller_id' in current_seller if isinstance(current_seller, dict) else None,
            "has_id_key": 'id' in current_seller if isinstance(current_seller, dict) else None,
            "extracted_seller_id": str(seller_id)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }


@router.get("/debug/page-info")
async def debug_page_info(
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Debug: Afficher les informations des pages Facebook"""
    try:
        from app.models.facebook import FacebookPage
        
        seller_id = extract_seller_id(current_seller)
        
        # Récupérer toutes les pages du vendeur
        pages = db.query(FacebookPage).filter(
            FacebookPage.seller_id == seller_id
        ).all()
        
        pages_data = []
        for page in pages:
            pages_data.append({
                "id": str(page.id),
                "page_id": page.page_id,
                "name": page.name,
                "is_selected": page.is_selected,
                "auto_reply_enabled": page.auto_reply_enabled,
                "has_token": bool(page.page_access_token),
                "token_preview": page.page_access_token[:30] + "..." if page.page_access_token else None,
                "token_length": len(page.page_access_token) if page.page_access_token else 0,
                "category": page.category,
                "fan_count": page.fan_count,
                "created_at": page.created_at.isoformat() if page.created_at else None
            })
        
        # Récupérer le token
        token = await get_facebook_token_from_db(seller_id, db)
        
        return {
            "success": True,
            "seller_id": str(seller_id),
            "total_pages": len(pages_data),
            "pages": pages_data,
            "extracted_token": {
                "has_token": bool(token),
                "token_preview": token[:30] + "..." if token else None,
                "token_length": len(token) if token else 0
            }
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }


# ================================
# ENDPOINT DE SANTÉ
# ================================

@router.get("/health")
async def messenger_health(
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Vérifie la santé du service Messenger"""
    try:
        seller_id = extract_seller_id(current_seller)
        
        # Vérifier la connexion à la base
        from sqlalchemy import text
        db_status = "healthy"
        try:
            db.execute(text("SELECT 1"))
        except:
            db_status = "unhealthy"
        
        # Vérifier le token
        token = await get_facebook_token_from_db(seller_id, db)
        token_status = "configured" if token else "not_configured"
        
        # Vérifier les permissions
        permissions_status = "unknown"
        if token:
            try:
                messenger_service = FacebookMessengerService(db)
                permissions_ok = await messenger_service._check_messenger_permissions(token)
                permissions_status = "granted" if permissions_ok else "missing"
            except:
                permissions_status = "check_failed"
        
        return {
            "success": True,
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "components": {
                "database": db_status,
                "token": token_status,
                "permissions": permissions_status
            },
            "seller_id": str(seller_id),
            "requirements": [
                "✅ Database connection",
                "✅ Facebook token configured" if token else "❌ Facebook token configured",
                "✅ Messenger permissions" if permissions_status == "granted" else f"⚠️  Messenger permissions ({permissions_status})"
            ]
        }
        
    except Exception as e:
        logger.error(f"Erreur health check: {e}")
        return {
            "success": False,
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


