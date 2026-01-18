
from datetime import datetime, timedelta
import re
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status, BackgroundTasks
from fastapi.responses import JSONResponse
import httpx
from sqlalchemy.orm import Session, joinedload
from typing import Dict, List, Optional, Any
import logging
import json
from uuid import UUID
import asyncio

from app.db import SessionLocal, get_db
from app.models.facebook_reply import FacebookReplyHistory
from app.models.message_history import MessengerMessage
from app.models.order import Order
from app.models.product import Product
from app.services.facebook_auth import facebook_auth_service
from app.services.facebook_webhook import facebook_webhook_service
from app.services.facebook_graph_api import facebook_graph_service
from app.services import nlp_service
from app.schemas.facebook import (
    FacebookConnectRequest,
    FacebookConnectResponse,
    FacebookAuthResponse,
    FacebookPageResponse,
    FacebookWebhookChallenge,
    SelectPageRequest,
    SelectPageResponse,
    SyncRequest,
    FacebookCommentResponse as CommentResponse,
    WebhookSubscriptionRequest,
    PostListResponse,
    LiveVideoListResponse,
    PostDetailResponse,
    LiveVideoDetailResponse,
    CommentDetailResponse,
    FacebookPostWithCommentsResponse,
    FacebookLiveVideoWithCommentsResponse,
)
from app.models.facebook import (
    FacebookComment, FacebookLiveVideo, FacebookMessage, 
    FacebookPost, FacebookUser, FacebookPage, FacebookWebhookLog,
    FacebookWebhookSubscription, NLPProcessingLog
)
from app.core.security import get_current_seller
from app.core.config import settings
try:
    # Essaie d'importer depuis nlp si tu l'as créé
    from app.nlp import intent_detector
    logging.info("✅ IntentDetector importé depuis app.nlp")
except ImportError:
    # Fallback: définir un IntentDetector de base localement
    logging.warning("⚠️ Module nlp non trouvé, création IntentDetector local")
    
    class IntentResult:
        def __init__(self):
            self.intent_type = 'unknown'
            self.confidence = 0.0
            self.sentiment = 'neutral'
            self.extracted_products = []
            self.entities = {}
    
    class IntentDetector:
        async def analyze_comment(self, text: str) -> IntentResult:
            """Analyse simplifiée d'un commentaire"""
            result = IntentResult()
            text_lower = text.lower() if text else ""
            
            # Détection d'intention basique
            purchase_keywords = ['je veux', 'je prends', 'commande', 'achète', 'jp', 'je prens']
            if any(keyword in text_lower for keyword in purchase_keywords):
                result.intent_type = 'purchase'
                result.confidence = 0.7
            else:
                result.intent_type = 'unknown'
                result.confidence = 0.0
            
            # Extraction de codes produits
            import re
            product_codes = re.findall(r'\b[A-Z]{2,4}-[A-Z0-9]{2,6}\b', text)
            if product_codes:
                result.extracted_products = [{'name': code, 'quantity': 1, 'code': code} for code in product_codes]
            
            return result
    
    intent_detector = IntentDetector()

# ==================== HELPER FUNCTIONS ====================

async def _format_post_data(
    post: FacebookPost, 
    db: Session, 
    include_comments: bool = True, 
    comment_limit: int = 10,
    seller_id: Optional[str] = None
) -> Dict[str, Any]:
    """Formate les données d'un post Facebook avec ses commentaires"""
    try:
        # Base post data
        post_data = {
            "id": str(post.id),
            "facebook_post_id": post.facebook_post_id,
            "message": post.message or "",
            "story": post.story or "",
            "likes_count": post.likes_count or 0,
            "comments_count": post.comments_count or 0,
            "shares_count": post.shares_count or 0,
            "post_type": post.post_type or "post",
            "page_id": post.page_id,
            "created_at": post.created_at.isoformat() if post.created_at else None,
            "updated_at": post.updated_at.isoformat() if post.updated_at else None,
            "facebook_created_time": post.facebook_created_time.isoformat() if post.facebook_created_time else None,
            "comments": []
        }
        
        # Récupérer les commentaires si demandé
        if include_comments and post.facebook_post_id:
            filter_conditions = [FacebookComment.post_id == post.facebook_post_id]
            if seller_id:
                filter_conditions.append(FacebookComment.seller_id == seller_id)
            
            comments_query = db.query(FacebookComment).filter(*filter_conditions)
            comments = comments_query.order_by(FacebookComment.created_at.asc()).limit(comment_limit).all()
            
            for comment in comments:
                comment_data = {
                    "id": str(comment.id),
                    "message": comment.message or "",
                    "user_name": comment.user_name or "Inconnu",
                    "post_id": comment.post_id,
                    "status": comment.status or "new",
                    "intent": comment.intent or "UNPROCESSABLE",
                    "sentiment": comment.sentiment,
                    "priority": comment.priority or "low",
                    "detected_code_article": comment.detected_code_article,
                    "detected_quantity": comment.detected_quantity or 0,
                    "created_at": comment.created_at.isoformat() if comment.created_at else None,
                    "facebook_created_time": comment.facebook_created_time.isoformat() if comment.facebook_created_time else None,
                    "updated_at": comment.updated_at.isoformat() if comment.updated_at else None
                }
                post_data["comments"].append(comment_data)
        
        return post_data
        
    except Exception as e:
        logger.error(f"❌ Erreur formatage post {post.id if post else 'unknown'}: {e}")
        # Version de secours
        return {
            "id": str(post.id) if post else "",
            "facebook_post_id": post.facebook_post_id if post else "",
            "message": post.message if post else "",
            "story": post.story if post else "",
            "likes_count": post.likes_count if post else 0,
            "comments_count": post.comments_count if post else 0,
            "shares_count": post.shares_count if post else 0,
            "post_type": post.post_type if post else "post",
            "page_id": post.page_id if post else "",
            "created_at": post.created_at.isoformat() if post and post.created_at else None,
            "updated_at": post.updated_at.isoformat() if post and post.updated_at else None,
            "facebook_created_time": post.facebook_created_time.isoformat() if post and post.facebook_created_time else None,
            "comments": []
        }

async def _format_live_data(
    live: FacebookLiveVideo, 
    db: Session, 
    include_comments: bool = True, 
    comment_limit: int = 20
) -> Dict[str, Any]:
    """Formate les données d'un live avec ses commentaires"""
    live_data = {
        "id": str(live.id),
        "facebook_video_id": live.facebook_video_id,
        "title": live.title or "",
        "description": live.description or "",
        "status": live.status or "published",
        "stream_url": live.stream_url or "",
        "permalink_url": live.permalink_url or "",
        "created_at": live.created_at.isoformat() if live.created_at else None,
        "actual_start_time": live.actual_start_time.isoformat() if live.actual_start_time else None,
        "end_time": live.end_time.isoformat() if live.end_time else None,
        "viewers_count": live.viewers_count or 0,
        "duration": live.duration,
        "page_id": str(live.page_id),
        "auto_process_comments": live.auto_process_comments,
        "notify_on_new_orders": live.notify_on_new_orders,
        "comments": []
    }
    
    if include_comments:
        comments = db.query(FacebookComment).filter(
            FacebookComment.post_id == live.facebook_video_id
        ).order_by(FacebookComment.created_at.asc()).limit(comment_limit).all()
        
        for comment in comments:
            live_data["comments"].append({
                "id": comment.id,
                "message": comment.message or "",
                "user_name": comment.user_name or "Inconnu",
                "status": comment.status or "new",
                "intent": comment.intent or "UNPROCESSABLE",
                "sentiment": comment.sentiment,
                "priority": comment.priority or "low",
                "detected_code_article": comment.detected_code_article,
                "detected_quantity": comment.detected_quantity or 0,
                "created_at": comment.created_at.isoformat() if comment.created_at else None,
                "facebook_created_time": comment.facebook_created_time.isoformat() if comment.facebook_created_time else None
            })
    
    return live_data

async def _save_comment_from_api(
    comment_data: Dict, 
    seller_id: str, 
    page_id: str, 
    post_id: str, 
    db: Session
) -> bool:
    """Sauvegarde un commentaire depuis l'API Facebook"""
    try:
        comment_id = comment_data.get("id")
        if not comment_id:
            return False
        
        # Vérifier si le commentaire existe déjà
        existing = db.query(FacebookComment).filter(
            FacebookComment.id == comment_id
        ).first()
        
        if existing:
            return False
        
        # Analyser l'intention avec NLP
        message = comment_data.get("message", "")
        if nlp_service:
            nlp_result = nlp_service.extract_all(message)
        else:
            nlp_result = {
                "intent": "UNPROCESSABLE",
                "sentiment": "neutral",
                "priority_level": "low",
                "order_items": []
            }
        
        # Extraire les informations produit
        order_items = nlp_result.get("order_items", [])
        detected_code_article = None
        detected_quantity = None
        
        if order_items:
            first_item = order_items[0]
            detected_code_article = first_item.get("product")
            detected_quantity = first_item.get("quantity")
        
        # Créer le commentaire
        comment = FacebookComment(
            id=comment_id,
            seller_id=seller_id,
            post_id=post_id,
            page_id=page_id,
            user_name=comment_data.get("from", {}).get("name", "Inconnu"),
            message=message,
            facebook_created_time=datetime.fromisoformat(
                comment_data.get("created_time").replace("Z", "+00:00")
            ) if comment_data.get("created_time") else datetime.utcnow(),
            status="new",
            intent=nlp_result.get("intent"),
            sentiment=nlp_result.get("sentiment"),
            priority=nlp_result.get("priority_level", "low"),
            detected_code_article=detected_code_article,
            detected_quantity=detected_quantity,
            created_at=datetime.utcnow()
        )
        
        db.add(comment)
        return True
        
    except Exception as e:
        logger.warning(f"⚠️ Erreur sauvegarde commentaire API: {e}")
        return False

async def _sync_single_post(post_id: str, seller_id: str, db: Session) -> Optional[FacebookPost]:
    """Synchronise un post spécifique depuis Facebook"""
    try:
        # Trouver une page du seller pour récupérer le token
        page = db.query(FacebookPage).filter(
            FacebookPage.seller_id == seller_id,
            FacebookPage.is_selected == True
        ).first()
        
        if not page or not page.page_access_token:
            return None
        
        # Récupérer le post depuis Facebook
        post_data = await facebook_graph_service.get_post_details(
            post_id=post_id,
            access_token=page.page_access_token
        )
        
        if not post_data:
            return None
        
        # Créer le post
        post = FacebookPost(
            id=uuid.uuid4(),
            facebook_post_id=post_id,
            seller_id=seller_id,
            page_id=str(page.id),
            message=post_data.get("message", ""),
            story=post_data.get("story", ""),
            post_type=post_data.get("type", "post"),
            created_at=datetime.utcnow(),
            facebook_created_time=datetime.fromisoformat(
                post_data.get("created_time").replace("Z", "+00:00")
            ) if post_data.get("created_time") else None,
            likes_count=post_data.get("likes_count", 0),
            comments_count=post_data.get("comments_count", 0),
            shares_count=post_data.get("shares_count", 0)
        )
        
        db.add(post)
        db.commit()
        
        return post
        
    except Exception as e:
        logger.error(f"❌ Erreur synchronisation post {post_id}: {e}")
        db.rollback()
        return None

async def _sync_single_live(video_id: str, seller_id: str, db: Session) -> Optional[FacebookLiveVideo]:
    """Synchronise un live spécifique depuis Facebook"""
    try:
        # Trouver une page du seller pour récupérer le token
        page = db.query(FacebookPage).filter(
            FacebookPage.seller_id == seller_id,
            FacebookPage.is_selected == True
        ).first()
        
        if not page or not page.page_access_token:
            return None
        
        # Récupérer le live depuis Facebook
        live_data = await facebook_graph_service.get_live_details(
            video_id=video_id,
            access_token=page.page_access_token
        )
        
        if not live_data:
            return None
        
        # Créer le live
        live = FacebookLiveVideo(
            id=uuid.uuid4(),
            facebook_video_id=video_id,
            seller_id=seller_id,
            page_id=page.page_id,
            title=live_data.get("title", ""),
            description=live_data.get("description", ""),
            status=live_data.get("status", "published"),
            stream_url=live_data.get("stream_url", ""),
            permalink_url=live_data.get("permalink_url", ""),
            created_at=datetime.utcnow(),
            actual_start_time=datetime.fromisoformat(
                live_data.get("creation_time").replace("Z", "+00:00")
            ) if live_data.get("creation_time") else None,
            viewers_count=live_data.get("viewers", 0)
        )
        
        db.add(live)
        db.commit()
        
        return live
        
    except Exception as e:
        logger.error(f"❌ Erreur synchronisation live {video_id}: {e}")
        db.rollback()
        return None

# ==================== WEBHOOK PROCESSING FUNCTIONS ====================

async def process_webhook_async(webhook_log_id: UUID, body_json: dict, db: Session):
    """Traite le webhook de manière asynchrone"""
    try:
        # Récupérer le log
        webhook_log = db.query(FacebookWebhookLog).filter(
            FacebookWebhookLog.id == webhook_log_id
        ).first()
        if not webhook_log:
            logger.error(f"Log webhook {webhook_log_id} non trouvé")
            return
        
        # Parser l'événement webhook
        parsed_event = facebook_webhook_service.parse_webhook_event(body_json)
        
        if not parsed_event.get("success"):
            logger.warning(f"⚠️ Webhook non parsé correctement: {body_json.get('object')}")
            return
        
        # Extraire les données critiques pour Live Commerce
        critical_data = facebook_webhook_service.extract_critical_data(parsed_event)
        
        # Traiter chaque événement critique
        for event in critical_data.get("events", []):
            if event["type"] == "comment":
                await process_comment_event(event, db)
            elif event["type"] == "message":
                await process_message_event(event, db)
            elif event["type"] == "live_video":
                await process_live_video_event(event, db)
        
        # Marquer comme traité
        webhook_log.processed = True
        webhook_log.processed_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"✅ Webhook {webhook_log_id} traité avec succès - {len(critical_data.get('events', []))} événements")
        
    except Exception as e:
        logger.error(f"❌ Erreur traitement webhook async: {e}", exc_info=True)
        db.rollback()

async def process_comment_event(event: Dict[str, Any], db: Session):
    """Traite un événement commentaire"""
    try:
        comment_id = event.get("comment_id")
        post_id = event.get("post_id")
        page_id = event.get("page_id")
        message = event.get("message", "")
        user_name = event.get("sender_name", "Utilisateur inconnu")
        
        # Vérifier si le commentaire existe déjà
        existing_comment = db.query(FacebookComment).filter(
            FacebookComment.id == comment_id
        ).first()
        
        if existing_comment:
            logger.info(f"⚠️ Commentaire {comment_id} déjà existant")
            return
        
        # Vérifier si le service NLP est disponible
        if not nlp_service:
            logger.warning("⚠️ Service NLP non disponible, skip NLP analysis")
            nlp_result = {
                "intent": "UNPROCESSABLE",
                "sentiment": "neutral",
                "priority_level": "low",
                "order_items": []
            }
        else:
            # Analyser l'intention avec NLP
            nlp_result = nlp_service.extract_all(message)
        
        # Récupérer le seller_id depuis la page
        page = db.query(FacebookPage).filter(
            FacebookPage.page_id == page_id
        ).first()
        
        if not page:
            logger.warning(f"⚠️ Page {page_id} non trouvée pour commentaire {comment_id}")
            return
        
        # Créer le commentaire
        comment = FacebookComment(
            id=comment_id,
            seller_id=page.seller_id,
            post_id=post_id,
            page_id=str(page.id),
            user_name=user_name,
            message=message,
            facebook_created_time=datetime.utcnow(),
            status="new",
            intent=nlp_result.get("intent"),
            sentiment=nlp_result.get("sentiment"),
            priority=nlp_result.get("priority_level", "low"),
            created_at=datetime.utcnow()
        )
        
        # Extraire les informations produit depuis les items de commande
        order_items = nlp_result.get("order_items", [])
        if order_items:
            # Prendre le premier item pour l'article
            first_item = order_items[0]
            comment.detected_code_article = first_item.get("product")
            comment.detected_quantity = first_item.get("quantity")
        
        db.add(comment)
        db.commit()
        
        logger.info(f"✅ Commentaire sauvegardé: {comment_id} - Intent: {nlp_result.get('intent')}")
        
    except Exception as e:
        logger.error(f"❌ Erreur traitement commentaire: {e}", exc_info=True)
        db.rollback()

async def process_message_event(event: Dict[str, Any], db: Session):
    """Traite un événement message Messenger"""
    try:
        sender_id = event.get("sender_id")
        page_id = event.get("page_id")
        message_text = event.get("text", "")
        
        # Récupérer la page
        page = db.query(FacebookPage).filter(
            FacebookPage.page_id == page_id
        ).first()
        
        if not page:
            logger.warning(f"⚠️ Page {page_id} non trouvée pour message")
            return
        
        # Analyser l'intention avec NLP si disponible
        nlp_result = {}
        if nlp_service:
            nlp_result = nlp_service.extract_all(message_text)
        
        # Créer le message
        message = FacebookMessage(
            seller_id=page.seller_id,
            customer_facebook_id=sender_id,
            facebook_page_id=page_id,
            message_type="text",
            content=message_text,
            status="pending",
            direction="incoming",
            created_at=datetime.utcnow()
        )
        
        db.add(message)
        db.commit()
        
        logger.info(f"✅ Message sauvegardé: {sender_id} - Intent: {nlp_result.get('intent', 'UNPROCESSABLE')}")
        
    except Exception as e:
        logger.error(f"❌ Erreur traitement message: {e}", exc_info=True)
        db.rollback()

async def process_live_video_event(event: Dict[str, Any], db: Session):
    """Traite un événement live vidéo"""
    try:
        video_id = event.get("video_id")
        page_id = event.get("page_id")
        status = event.get("status")
        
        # Récupérer la page
        page = db.query(FacebookPage).filter(
            FacebookPage.page_id == page_id
        ).first()
        
        if not page:
            logger.warning(f"⚠️ Page {page_id} non trouvée pour live {video_id}")
            return
        
        # Vérifier si le live existe déjà
        existing_live = db.query(FacebookLiveVideo).filter(
            FacebookLiveVideo.facebook_video_id == video_id
        ).first()
        
        if existing_live:
            # Mettre à jour le live existant
            existing_live.status = status
            if status == "live":
                existing_live.actual_start_time = datetime.utcnow()
            elif status == "archived":
                existing_live.end_time = datetime.utcnow()
            existing_live.updated_at = datetime.utcnow()
        else:
            # Créer un nouveau live
            live = FacebookLiveVideo(
                seller_id=page.seller_id,
                facebook_video_id=video_id,
                page_id=page_id,
                status=status,
                auto_process_comments=True,
                notify_on_new_orders=True,
                created_at=datetime.utcnow()
            )
            db.add(live)
        
        db.commit()
        logger.info(f"✅ Live {video_id} mis à jour: {status}")
        
    except Exception as e:
        logger.error(f"❌ Erreur traitement live: {e}", exc_info=True)
        db.rollback()

# ==================== INITIALIZATION ====================

router = APIRouter()
logger = logging.getLogger(__name__)

# ==================== AUTHENTICATION ENDPOINTS ====================

@router.get("/login", response_model=FacebookConnectResponse)
async def facebook_login(
    fb_request: FacebookConnectRequest = Depends(),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Génère l'URL OAuth pour la connexion Facebook"""
    try:
        # Vérifier si l'utilisateur a déjà un compte Facebook connecté
        existing_user = db.query(FacebookUser).filter(
            FacebookUser.seller_id == current_seller.id,
            FacebookUser.is_active == True
        ).first()
        
        if existing_user:
            raise HTTPException(
                status_code=400,
                detail="Un compte Facebook est déjà connecté. Déconnectez-vous d'abord."
            )
        
        # Générer l'URL OAuth
        state = fb_request.state or str(current_seller.id)
        auth_url = facebook_auth_service.get_oauth_url(state)
        
        return FacebookConnectResponse(
            success=True,
            auth_url=auth_url,
            state=state
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erreur génération URL OAuth: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Erreur lors de la connexion à Facebook"
        )

@router.get("/callback", response_model=FacebookAuthResponse)
async def facebook_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db)
):
    """Callback OAuth Facebook"""
    try:
        logger.info(f"🔄 Callback Facebook reçu - Code: {code[:20]}..., State: {state}")
        
        # 1. Vérifier que le code n'est pas vide
        if not code or code.strip() == "":
            raise HTTPException(
                status_code=400,
                detail="Code d'autorisation manquant ou invalide"
            )
        
        # 2. Échanger le code contre un token
        token_data = await facebook_auth_service.exchange_code_for_token(code)
        
        if not token_data or "access_token" not in token_data:
            raise HTTPException(
                status_code=400,
                detail="Impossible d'obtenir le token d'accès Facebook"
            )
        
        access_token = token_data["access_token"]
        
        # 3. Récupérer les infos utilisateur
        user_info = await facebook_auth_service.get_user_info(access_token)
        
        if not user_info or "id" not in user_info:
            raise HTTPException(
                status_code=400,
                detail="Impossible de récupérer les informations utilisateur Facebook"
            )
        
        # 4. Récupérer les pages
        pages = []
        try:
            pages = await facebook_auth_service.get_user_pages(access_token)
            logger.info(f"📄 {len(pages)} pages récupérées")
        except Exception as pages_error:
            logger.warning(f"⚠️ Pages non récupérées: {pages_error}")
        
        # 5. Vérifier et parser le state (seller_id)
        try:
            seller_id = UUID(state)
        except ValueError:
            logger.error(f"❌ State invalide: {state}")
            raise HTTPException(
                status_code=400,
                detail="État d'authentification invalide"
            )
        
        # 6. Vérifier si l'utilisateur existe déjà
        existing_user = db.query(FacebookUser).filter(
            FacebookUser.facebook_user_id == user_info["id"],
            FacebookUser.seller_id == seller_id
        ).first()
        
        if existing_user:
            # Mettre à jour l'utilisateur existant
            existing_user.long_lived_token = access_token
            existing_user.token_expires_at = facebook_auth_service.calculate_token_expiry(
                token_data.get("expires_in", 7200)
            )
            existing_user.is_active = True
            existing_user.updated_at = datetime.utcnow()
            facebook_user = existing_user
            logger.info(f"🔄 Utilisateur Facebook mis à jour: {user_info['id']}")
        else:
            # Créer un nouvel utilisateur
            facebook_user = FacebookUser(
                id=uuid.uuid4(),
                facebook_user_id=user_info["id"],
                name=user_info.get("name"),
                first_name=user_info.get("first_name"),
                last_name=user_info.get("last_name"),
                email=user_info.get("email"),
                profile_pic_url=user_info.get("profile_pic_url"),
                long_lived_token=access_token,
                token_expires_at=facebook_auth_service.calculate_token_expiry(
                    token_data.get("expires_in", 7200)
                ),
                seller_id=seller_id,
                is_active=True,
                created_at=datetime.utcnow()
            )
            db.add(facebook_user)
        
        db.flush()
        
        # 7. Sauvegarder les pages
        for page_data in pages:
            # Vérifier si la page existe déjà
            existing_page = db.query(FacebookPage).filter(
                FacebookPage.page_id == page_data["id"],
                FacebookPage.seller_id == seller_id
            ).first()
            
            if existing_page:
                # Mettre à jour la page existante
                existing_page.name = page_data.get("name", "Page sans nom")
                existing_page.category = page_data.get("category")
                existing_page.fan_count = page_data.get("fan_count", 0)
                existing_page.page_access_token = page_data.get("access_token", "")
                existing_page.token_expires_at = facebook_auth_service.calculate_token_expiry(
                    60 * 24 * 60 * 60  # 60 jours
                )
                existing_page.updated_at = datetime.utcnow()
            else:
                # Créer une nouvelle page
                fb_page = FacebookPage(
                    id=uuid.uuid4(),
                    page_id=page_data["id"],
                    name=page_data.get("name", "Page sans nom"),
                    category=page_data.get("category"),
                    fan_count=page_data.get("fan_count", 0),
                    page_access_token=page_data.get("access_token", ""),
                    token_expires_at=facebook_auth_service.calculate_token_expiry(
                        60 * 24 * 60 * 60
                    ),
                    facebook_user_id=facebook_user.id,
                    seller_id=seller_id,
                    is_selected=False,
                    auto_reply_enabled=False,
                    auto_process_comments=True,
                    created_at=datetime.utcnow()
                )
                db.add(fb_page)
        
        db.commit()
        
        # 8. Préparer la réponse
        user_info_data = {
            "facebook_user_id": user_info["id"],
            "name": user_info.get("name"),
            "first_name": user_info.get("first_name"),
            "last_name": user_info.get("last_name"),
            "email": user_info.get("email"),
            "profile_pic_url": user_info.get("profile_pic_url"),
        }
        
        formatted_pages = []
        for page in pages:
            formatted_pages.append({
                "page_id": page["id"],
                "name": page.get("name", "Page sans nom"),
                "category": page.get("category"),
                "fan_count": page.get("fan_count", 0),
                "access_token": page.get("access_token", ""),
                "is_selected": False
            })
        
        return FacebookAuthResponse(
            success=True,
            message=f"Connexion Facebook réussie - {len(pages)} pages disponibles",
            user_info=user_info_data,
            pages=formatted_pages
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erreur callback Facebook: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la connexion: {str(e)}"
        )

# ==================== PAGES MANAGEMENT ENDPOINTS ====================

@router.get("/pages", response_model=List[FacebookPageResponse])
async def get_facebook_pages(
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Récupère toutes les pages Facebook du vendeur"""
    try:
        pages = db.query(FacebookPage).filter(
            FacebookPage.seller_id == current_seller.id
        ).all()
        
        return [
            FacebookPageResponse(
                id=page.id,
                page_id=page.page_id,
                name=page.name,
                category=page.category,
                fan_count=page.fan_count,
                is_selected=page.is_selected,
                cover_photo_url=page.cover_photo_url,
                profile_pic_url=page.profile_pic_url,
                created_at=page.created_at.isoformat() if page.created_at else None
            )
            for page in pages
        ]
        
    except Exception as e:
        logger.error(f"❌ Erreur récupération pages: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/pages/select", response_model=SelectPageResponse)
async def select_facebook_page(
    request: SelectPageRequest,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Sélectionne une page Facebook comme page active et configure l'auto-reply"""
    try:
        # Désélectionner toutes les pages du vendeur
        db.query(FacebookPage).filter(
            FacebookPage.seller_id == current_seller.id
        ).update({"is_selected": False})
        
        # Sélectionner la page spécifiée
        page = db.query(FacebookPage).filter(
            FacebookPage.page_id == request.page_id,
            FacebookPage.seller_id == current_seller.id
        ).first()
        
        if not page:
            raise HTTPException(status_code=404, detail="Page non trouvée")
        
        # CORRECTION ICI : Mettre à jour auto_reply_enabled depuis la requête
        page.is_selected = True
        
        # Si auto_reply_enabled est fourni dans la requête, le mettre à jour
        if hasattr(request, 'auto_reply_enabled'):
            page.auto_reply_enabled = request.auto_reply_enabled
            logger.info(f"✅ Auto-reply mis à jour: {request.auto_reply_enabled}")
        else:
            # Par défaut, activer l'auto-reply quand on sélectionne une page
            page.auto_reply_enabled = True
            logger.info("✅ Auto-reply activé par défaut")
        
        page.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(page)
        
        return SelectPageResponse(
            success=True,
            message=f"Page {page.name} sélectionnée avec succès",
            page=FacebookPageResponse(
                id=page.id,
                page_id=page.page_id,
                name=page.name,
                category=page.category,
                fan_count=page.fan_count,
                is_selected=True,
                auto_reply_enabled=page.auto_reply_enabled,  # <-- AJOUTER CETTE LIGNE
                cover_photo_url=page.cover_photo_url,
                profile_pic_url=page.profile_pic_url
            )
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Erreur sélection page: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ==================== POSTS ENDPOINTS ====================

@router.get("/posts", response_model=PostListResponse)
async def get_facebook_posts(
    page_id: Optional[str] = Query(None, description="ID de la page Facebook"),
    limit: int = Query(20, ge=1, le=100, description="Nombre maximum de posts à récupérer"),
    offset: int = Query(0, ge=0, description="Offset pour la pagination"),
    include_comments: bool = Query(True, description="Inclure les commentaires"),
    comment_limit: int = Query(10, ge=1, le=50, description="Nombre maximum de commentaires par post"),
    since: Optional[datetime] = Query(None, description="Date de début pour filtrer les posts"),
    until: Optional[datetime] = Query(None, description="Date de fin pour filtrer les posts"),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Récupère les publications Facebook avec leurs commentaires"""
    try:
        # Récupérer la page sélectionnée
        if page_id:
            page = db.query(FacebookPage).filter(
                FacebookPage.page_id == page_id,
                FacebookPage.seller_id == current_seller.id
            ).first()
        else:
            # Utiliser la page sélectionnée par défaut
            page = db.query(FacebookPage).filter(
                FacebookPage.seller_id == current_seller.id,
                FacebookPage.is_selected == True
            ).first()
        
        if not page:
            raise HTTPException(
                status_code=404,
                detail="Aucune page Facebook trouvée. Veuillez sélectionner une page d'abord."
            )
        
        # Construire la requête de base pour les posts
        query = db.query(FacebookPost).filter(
            FacebookPost.seller_id == current_seller.id,
            FacebookPost.page_id == str(page.id)
        )
        
        # Appliquer les filtres de date
        if since:
            query = query.filter(FacebookPost.created_at >= since)
        if until:
            query = query.filter(FacebookPost.created_at <= until)
        
        # Compter le total
        total = query.count()
        
        # Récupérer les posts avec pagination
        posts = query.order_by(FacebookPost.created_at.desc()).offset(offset).limit(limit).all()
        
        posts_data = []
        for post in posts:
            post_data = await _format_post_data(
                post=post,
                db=db,
                include_comments=include_comments,
                comment_limit=comment_limit,
                seller_id=current_seller.id
            )
            posts_data.append(post_data)
        
        return PostListResponse(
            success=True,
            count=len(posts_data),
            total=total,
            page_id=page.page_id,
            page_name=page.name,
            posts=posts_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erreur récupération des posts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/posts/{post_id}", response_model=PostDetailResponse)
async def get_facebook_post_detail(
    post_id: str,
    include_comments: bool = Query(True, description="Inclure les commentaires"),
    comment_limit: int = Query(50, ge=1, le=100, description="Nombre maximum de commentaires"),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Récupère une publication spécifique avec tous ses détails et commentaires"""
    try:
        # Récupérer le post
        post = db.query(FacebookPost).filter(
            FacebookPost.facebook_post_id == post_id,
            FacebookPost.seller_id == current_seller.id
        ).first()
        
        if not post:
            # Essayer de synchroniser le post depuis Facebook
            post = await _sync_single_post(post_id, current_seller.id, db)
            if not post:
                raise HTTPException(
                    status_code=404,
                    detail="Publication non trouvée"
                )
        
        post_data = await _format_post_data(
            post=post, 
            db=db, 
            include_comments=include_comments, 
            comment_limit=comment_limit,
            seller_id=current_seller.id
        )
        
        # Récupérer les statistiques supplémentaires si disponible
        try:
            page = db.query(FacebookPage).filter(
                FacebookPage.id == UUID(post.page_id)
            ).first()
            
            if page and page.page_access_token:
                stats = await facebook_graph_service._make_request(
                    "GET",
                    f"{post.facebook_post_id}/insights",
                    params={
                        "metric": "post_impressions,post_engaged_users,post_reactions_by_type_total",
                        "access_token": page.page_access_token
                    }
                )
                post_data["insights"] = stats
        except Exception as e:
            logger.warning(f"⚠️ Impossible de récupérer les statistiques: {e}")
            post_data["insights"] = {}
        
        return PostDetailResponse(
            success=True,
            post=post_data,
            comments_count=post_data.get("comments_count", 0),
            reactions_count=post_data.get("likes_count", 0)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erreur récupération du post {post_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ==================== LIVE VIDEOS ENDPOINTS ====================

@router.get("/live-videos", response_model=LiveVideoListResponse)
async def get_facebook_live_videos(
    page_id: Optional[str] = Query(None, description="ID de la page Facebook"),
    limit: int = Query(20, ge=1, le=100, description="Nombre maximum de lives à récupérer"),
    offset: int = Query(0, ge=0, description="Offset pour la pagination"),
    include_comments: bool = Query(True, description="Inclure les commentaires"),
    comment_limit: int = Query(20, ge=1, le=100, description="Nombre maximum de commentaires par live"),
    status: Optional[str] = Query(None, description="Filtrer par statut (live, published, archived)"),
    since: Optional[datetime] = Query(None, description="Date de début pour filtrer les lives"),
    until: Optional[datetime] = Query(None, description="Date de fin pour filtrer les lives"),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Récupère les lives Facebook avec leurs commentaires"""
    try:
        # Récupérer la page sélectionnée
        if page_id:
            page = db.query(FacebookPage).filter(
                FacebookPage.page_id == page_id,
                FacebookPage.seller_id == current_seller.id
            ).first()
        else:
            # Utiliser la page sélectionnée par défaut
            page = db.query(FacebookPage).filter(
                FacebookPage.seller_id == current_seller.id,
                FacebookPage.is_selected == True
            ).first()
        
        if not page:
            raise HTTPException(
                status_code=404,
                detail="Aucune page Facebook trouvée. Veuillez sélectionner une page d'abord."
            )
        
        # Construire la requête de base pour les lives
        query = db.query(FacebookLiveVideo).filter(
            FacebookLiveVideo.seller_id == current_seller.id,
            FacebookLiveVideo.page_id == page.page_id
        )
        
        # Appliquer les filtres
        if status:
            query = query.filter(FacebookLiveVideo.status == status)
        if since:
            query = query.filter(FacebookLiveVideo.created_at >= since)
        if until:
            query = query.filter(FacebookLiveVideo.created_at <= until)
        
        # Compter le total
        total = query.count()
        
        # Récupérer les lives avec pagination
        lives = query.order_by(FacebookLiveVideo.created_at.desc()).offset(offset).limit(limit).all()
        
        lives_data = []
        for live in lives:
            live_data = await _format_live_data(live, db, include_comments, comment_limit)
            lives_data.append(live_data)
        
        return LiveVideoListResponse(
            success=True,
            count=len(lives_data),
            total=total,
            page_id=page.page_id,
            page_name=page.name,
            live_videos=lives_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erreur récupération des lives: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/live-videos/{video_id}", response_model=LiveVideoDetailResponse)
async def get_facebook_live_detail(
    video_id: str,
    include_comments: bool = Query(True, description="Inclure les commentaires"),
    comment_limit: int = Query(100, ge=1, le=200, description="Nombre maximum de commentaires"),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Récupère un live spécifique avec tous ses détails et commentaires"""
    try:
        # Récupérer le live
        live = db.query(FacebookLiveVideo).filter(
            FacebookLiveVideo.facebook_video_id == video_id,
            FacebookLiveVideo.seller_id == current_seller.id
        ).first()
        
        if not live:
            # Essayer de synchroniser le live depuis Facebook
            live = await _sync_single_live(video_id, current_seller.id, db)
            if not live:
                raise HTTPException(
                    status_code=404,
                    detail="Live vidéo non trouvé"
                )
        
        live_data = await _format_live_data(live, db, include_comments, comment_limit)
        
        # Récupérer les statistiques supplémentaires si disponible
        try:
            page = db.query(FacebookPage).filter(
                FacebookPage.page_id == live.page_id
            ).first()
            
            if page and page.page_access_token:
                stats = await facebook_graph_service._make_request(
                    "GET",
                    f"{video_id}/video_insights",
                    params={
                        "metric": "total_video_views,total_video_time_watched",
                        "access_token": page.page_access_token
                    }
                )
                live_data["insights"] = stats
        except Exception as e:
            logger.warning(f"⚠️ Impossible de récupérer les statistiques du live: {e}")
            live_data["insights"] = {}
        
        return LiveVideoDetailResponse(
            success=True,
            live_video=live_data,
            comments_count=live_data.get("comments_count", 0),
            viewers_count=live_data.get("viewers_count", 0)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erreur récupération du live {video_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ==================== COMMENTS ENDPOINTS ====================

@router.get("/posts/{post_id}/comments", response_model=List[CommentDetailResponse])
async def get_post_comments(
    post_id: str,
    limit: int = Query(100, ge=1, le=500, description="Nombre maximum de commentaires"),
    offset: int = Query(0, ge=0, description="Offset pour la pagination"),
    status: Optional[str] = Query(None, description="Filtrer par statut"),
    intent: Optional[str] = Query(None, description="Filtrer par intention détectée"),
    priority: Optional[str] = Query(None, description="Filtrer par priorité"),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Récupère tous les commentaires d'une publication spécifique"""
    try:
        # Vérifier que le post existe
        post = db.query(FacebookPost).filter(
            FacebookPost.facebook_post_id == post_id,
            FacebookPost.seller_id == current_seller.id
        ).first()
        
        if not post:
            raise HTTPException(
                status_code=404,
                detail="Publication non trouvée"
            )
        
        # Construire la requête pour les commentaires
        query = db.query(FacebookComment).filter(
            FacebookComment.post_id == post_id,
            FacebookComment.seller_id == current_seller.id
        )
        
        # Appliquer les filtres
        if status:
            query = query.filter(FacebookComment.status == status)
        if intent:
            query = query.filter(FacebookComment.intent == intent)
        if priority:
            query = query.filter(FacebookComment.priority == priority)
        
        # Compter le total
        total = query.count()
        
        # Récupérer les commentaires avec pagination
        comments = query.order_by(FacebookComment.created_at.asc()).offset(offset).limit(limit).all()
        
        comments_data = []
        for comment in comments:
            comments_data.append({
                "id": comment.id,
                "message": comment.message or "",
                "user_name": comment.user_name or "Inconnu",
                "post_id": comment.post_id,
                "status": comment.status or "new",
                "intent": comment.intent or "UNPROCESSABLE",
                "sentiment": comment.sentiment,
                "priority": comment.priority or "low",
                "detected_code_article": comment.detected_code_article,
                "detected_quantity": comment.detected_quantity or 0,
                "created_at": comment.created_at.isoformat() if comment.created_at else None,
                "facebook_created_time": comment.facebook_created_time.isoformat() if comment.facebook_created_time else None
            })
        
        return comments_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erreur récupération des commentaires pour post {post_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/live-videos/{video_id}/comments", response_model=List[CommentDetailResponse])
async def get_live_comments(
    video_id: str,
    limit: int = Query(200, ge=1, le=1000, description="Nombre maximum de commentaires"),
    offset: int = Query(0, ge=0, description="Offset pour la pagination"),
    status: Optional[str] = Query(None, description="Filtrer par statut"),
    intent: Optional[str] = Query(None, description="Filtrer par intention détectée"),
    priority: Optional[str] = Query(None, description="Filtrer par priorité"),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Récupère tous les commentaires d'un live spécifique"""
    try:
        # Vérifier que le live existe
        live = db.query(FacebookLiveVideo).filter(
            FacebookLiveVideo.facebook_video_id == video_id,
            FacebookLiveVideo.seller_id == current_seller.id
        ).first()
        
        if not live:
            raise HTTPException(
                status_code=404,
                detail="Live vidéo non trouvé"
            )
        
        # Pour les lives, les commentaires sont stockés avec post_id = video_id
        query = db.query(FacebookComment).filter(
            FacebookComment.post_id == video_id,
            FacebookComment.seller_id == current_seller.id
        )
        
        # Appliquer les filtres
        if status:
            query = query.filter(FacebookComment.status == status)
        if intent:
            query = query.filter(FacebookComment.intent == intent)
        if priority:
            query = query.filter(FacebookComment.priority == priority)
        
        # Compter le total
        total = query.count()
        
        # Récupérer les commentaires avec pagination
        comments = query.order_by(FacebookComment.created_at.asc()).offset(offset).limit(limit).all()
        
        comments_data = []
        for comment in comments:
            comments_data.append({
                "id": comment.id,
                "message": comment.message or "",
                "user_name": comment.user_name or "Inconnu",
                "post_id": comment.post_id,
                "status": comment.status or "new",
                "intent": comment.intent or "UNPROCESSABLE",
                "sentiment": comment.sentiment,
                "priority": comment.priority or "low",
                "detected_code_article": comment.detected_code_article,
                "detected_quantity": comment.detected_quantity or 0,
                "created_at": comment.created_at.isoformat() if comment.created_at else None,
                "facebook_created_time": comment.facebook_created_time.isoformat() if comment.facebook_created_time else None
            })
        
        return comments_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erreur récupération des commentaires pour live {video_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ==================== SYNC ENDPOINTS ====================

@router.post("/sync/posts")
async def sync_facebook_posts(
    page_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    since_days: int = Query(90, ge=1, le=365),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Synchronise les publications Facebook depuis l'API Graph"""
    try:
        # Récupérer la page
        if page_id:
            page = db.query(FacebookPage).filter(
                FacebookPage.page_id == page_id,
                FacebookPage.seller_id == current_seller.id
            ).first()
        else:
            page = db.query(FacebookPage).filter(
                FacebookPage.seller_id == current_seller.id,
                FacebookPage.is_selected == True
            ).first()
        
        if not page:
            raise HTTPException(
                status_code=404,
                detail="Page Facebook non trouvée"
            )
        
        if not page.page_access_token:
            raise HTTPException(
                status_code=400,
                detail="Token de page manquant. Veuillez reconnecter la page à Facebook."
            )
        
        logger.info("=" * 60)
        logger.info(f"🔄 DÉBUT Synchronisation Facebook Posts")
        logger.info(f"   Page: {page.name} (ID: {page.page_id})")
        logger.info(f"   Paramètres: limit={limit}, since_days={since_days}")
        
        # Calculer la date de début
        since = None
        if since_days < 3650:  # Si moins de 10 ans
            since = datetime.utcnow() - timedelta(days=since_days)
            logger.info(f"   Date depuis: {since}")
        else:
            logger.info(f"   Pas de filtre de date (since_days={since_days})")
        
        # Récupérer les posts
        posts, paging = await facebook_graph_service.get_page_posts(
            page_id=page.page_id,
            access_token=page.page_access_token,
            limit=limit,
            since=since
        )
        
        logger.info(f"📥 {len(posts)} posts récupérés de Facebook API")
        
        if not posts:
            logger.warning("⚠️ Aucun post récupéré depuis Facebook")
            return {
                "success": True,
                "message": "Aucun post à synchroniser",
                "posts_synced": 0,
                "comments_synced": 0,
                "page": page.name
            }
        
        posts_saved = 0
        total_comments_saved = 0
        
        for idx, post_data in enumerate(posts):
            try:
                post_id = post_data.get("id")
                if not post_id:
                    logger.warning(f"⚠️ Post sans ID, ignoré")
                    continue
                
                # Extraction des données du post
                message = post_data.get("message", "") or post_data.get("story", "") or ""
                story = post_data.get("story", "")
                
                logger.info(f"📝 [{idx+1}/{len(posts)}] Post {post_id}:")
                logger.info(f"   Message: '{message[:80]}...'" if message else "   (Pas de message)")
                
                # Récupérer les stats (likes, comments, shares)
                stats = await facebook_graph_service.get_post_stats(
                    post_id=post_id,
                    access_token=page.page_access_token
                )
                
                likes_count = stats["likes_count"]
                comments_count = stats["comments_count"]
                shares_count = stats["shares_count"]
                
                logger.info(f"   Stats: 👍{likes_count} 💬{comments_count} 🔄{shares_count}")
                
                # Vérifier si le post existe déjà
                existing_post = db.query(FacebookPost).filter(
                    FacebookPost.facebook_post_id == post_id,
                    FacebookPost.seller_id == current_seller.id
                ).first()
                
                if existing_post:
                    # Supprimer les anciens commentaires
                    db.query(FacebookComment).filter(
                        FacebookComment.post_id == post_id,
                        FacebookComment.seller_id == current_seller.id
                    ).delete()
                    
                    # Mettre à jour le post existant
                    existing_post.message = message
                    existing_post.story = story
                    existing_post.updated_at = datetime.utcnow()
                    existing_post.likes_count = likes_count
                    existing_post.comments_count = comments_count
                    existing_post.shares_count = shares_count
                    
                    # Mettre à jour la date
                    if post_data.get("created_time"):
                        try:
                            facebook_created_time = datetime.fromisoformat(
                                post_data["created_time"].replace("Z", "+00:00")
                            )
                            existing_post.facebook_created_time = facebook_created_time
                        except:
                            pass
                    
                    post_obj = existing_post
                    logger.info(f"   🔄 Post existant mis à jour (commentaires supprimés)")
                else:
                    # Créer un nouveau post
                    facebook_created_time = None
                    if post_data.get("created_time"):
                        try:
                            facebook_created_time = datetime.fromisoformat(
                                post_data["created_time"].replace("Z", "+00:00")
                            )
                        except:
                            pass
                    
                    post_obj = FacebookPost(
                        id=uuid.uuid4(),
                        facebook_post_id=post_id,
                        seller_id=current_seller.id,
                        page_id=str(page.id),
                        message=message,
                        story=story,
                        post_type="post",
                        created_at=datetime.utcnow(),
                        facebook_created_time=facebook_created_time,
                        likes_count=likes_count,
                        comments_count=comments_count,
                        shares_count=shares_count
                    )
                    db.add(post_obj)
                    logger.info(f"   ✨ Nouveau post créé en base")
                
                db.flush()
                posts_saved += 1
                
                # Récupérer les commentaires si nécessaire
                post_comments_saved = 0
                if comments_count > 0:
                    logger.info(f"   📝 Récupération des commentaires ({comments_count} au total)")
                    
                    # Récupérer les commentaires
                    comments, comment_paging = await facebook_graph_service.get_post_comments(
                        post_id=post_id,
                        access_token=page.page_access_token,
                        limit=min(comments_count, 100)
                    )
                    
                    logger.info(f"   📥 {len(comments)} commentaires récupérés de l'API")
                    
                    if comments:
                        for comment_data in comments:
                            try:
                                comment_saved = await _save_comment_from_api(
                                    comment_data, 
                                    current_seller.id, 
                                    str(page.id),
                                    post_id,
                                    db
                                )
                                if comment_saved:
                                    post_comments_saved += 1
                            except Exception as comment_error:
                                logger.warning(f"      ⚠️ Erreur commentaire: {comment_error}")
                                continue
                        
                        logger.info(f"   💾 {post_comments_saved} commentaires sauvegardés pour ce post")
                    else:
                        logger.info(f"   ℹ️  Aucun commentaire récupéré")
                    
                    total_comments_saved += post_comments_saved
                else:
                    logger.info(f"   ℹ️  Aucun commentaire pour ce post")
                
                # Commit par lots
                if posts_saved % 10 == 0:
                    db.commit()
                    logger.info(f"   📊 Progression: {posts_saved} posts, {total_comments_saved} commentaires...")
                    
            except Exception as e:
                logger.error(f"   ❌ Erreur traitement post {post_data.get('id', 'unknown')}: {e}", exc_info=True)
                db.rollback()
                continue
        
        # Commit final
        db.commit()
        
        logger.info("=" * 60)
        logger.info(f"✅ SYNCHRONISATION TERMINÉE")
        logger.info(f"   Posts synchronisés: {posts_saved}")
        logger.info(f"   Commentaires synchronisés: {total_comments_saved}")
        logger.info(f"   Page: {page.name}")
        logger.info("=" * 60)
        
        return {
            "success": True,
            "message": f"Synchronisation réussie: {posts_saved} posts, {total_comments_saved} commentaires",
            "posts_synced": posts_saved,
            "comments_synced": total_comments_saved,
            "page": page.name
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ ERREUR SYNCHRONISATION: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Erreur lors de la synchronisation: {str(e)}"
        )

@router.post("/sync/live-videos")
async def sync_facebook_live_videos(
    page_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    since_days: int = Query(30, ge=1, le=90),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Synchronise les lives Facebook depuis l'API Graph"""
    try:
        # Récupérer la page
        if page_id:
            page = db.query(FacebookPage).filter(
                FacebookPage.page_id == page_id,
                FacebookPage.seller_id == current_seller.id
            ).first()
        else:
            page = db.query(FacebookPage).filter(
                FacebookPage.seller_id == current_seller.id,
                FacebookPage.is_selected == True
            ).first()
        
        if not page:
            raise HTTPException(
                status_code=404,
                detail="Page Facebook non trouvée"
            )
        
        if not page.page_access_token:
            raise HTTPException(
                status_code=400,
                detail="Token de page manquant. Veuillez reconnecter la page à Facebook."
            )
        
        logger.info(f"🔄 Synchronisation des lives pour page: {page.name}")
        
        # Récupérer les lives depuis Facebook Graph API
        live_videos = await facebook_graph_service.get_live_videos(
            page_id=page.page_id,
            access_token=page.page_access_token,
            limit=limit
        )
        
        logger.info(f"📥 {len(live_videos)} lives récupérés de Facebook")
        
        lives_saved = 0
        comments_saved = 0
        
        for live_data in live_videos:
            try:
                video_id = live_data.get("id")
                if not video_id:
                    continue
                
                # Extraction des données
                title = live_data.get("title", "")
                description = live_data.get("description", "")
                status = live_data.get("status", "published")
                viewers = live_data.get("live_views", 0)
                
                logger.info(f"📺 Live {video_id}:")
                logger.info(f"   Titre: '{title[:50]}...'")
                logger.info(f"   Statut: {status}, Spectateurs: {viewers}")
                
                # Vérifier si le live existe déjà
                existing_live = db.query(FacebookLiveVideo).filter(
                    FacebookLiveVideo.facebook_video_id == video_id,
                    FacebookLiveVideo.seller_id == current_seller.id
                ).first()
                
                if existing_live:
                    # Mettre à jour le live existant
                    existing_live.title = title
                    existing_live.description = description
                    existing_live.status = status
                    existing_live.updated_at = datetime.utcnow()
                    existing_live.viewers_count = viewers
                    live_obj = existing_live
                    logger.info(f"   🔄 Live mis à jour")
                else:
                    # Créer un nouveau live
                    live_obj = FacebookLiveVideo(
                        id=uuid.uuid4(),
                        facebook_video_id=video_id,
                        seller_id=current_seller.id,
                        page_id=page.page_id,
                        title=title,
                        description=description,
                        status=status,
                        stream_url=live_data.get("stream_url", ""),
                        permalink_url=live_data.get("permalink_url", ""),
                        created_at=datetime.utcnow(),
                        actual_start_time=datetime.fromisoformat(
                            live_data.get("creation_time").replace("Z", "+00:00")
                        ) if live_data.get("creation_time") else None,
                        viewers_count=viewers
                    )
                    db.add(live_obj)
                    logger.info(f"   ✨ Nouveau live créé")
                
                db.flush()
                lives_saved += 1
                
                # Synchroniser les commentaires pour ce live
                try:
                    comments = await facebook_graph_service.get_live_comments(
                        video_id=video_id,
                        access_token=page.page_access_token,
                        limit=100
                    )
                    
                    if comments:
                        logger.info(f"   📝 {len(comments)} commentaires récupérés pour ce live")
                        
                        for comment_data in comments:
                            comment_saved = await _save_comment_from_api(
                                comment_data, 
                                current_seller.id, 
                                str(page.id),
                                video_id,
                                db
                            )
                            if comment_saved:
                                comments_saved += 1
                    else:
                        logger.info(f"   ℹ️  Aucun commentaire pour ce live")
                        
                except Exception as comment_error:
                    logger.warning(f"   ⚠️ Erreur récupération commentaires live: {comment_error}")
                
                # Commit par lots
                if lives_saved % 3 == 0:
                    db.commit()
                    logger.info(f"    📊 Progression: {lives_saved} lives, {comments_saved} commentaires...")
                    
            except Exception as e:
                logger.warning(f"    ⚠️ Erreur sauvegarde live {live_data.get('id', 'unknown')}: {e}")
                continue
        
        # Commit final
        db.commit()
        
        logger.info(f"✅ Synchronisation terminée: {lives_saved} lives, {comments_saved} commentaires")
        
        return {
            "success": True,
            "message": f"Synchronisation réussie: {lives_saved} lives, {comments_saved} commentaires",
            "lives_synced": lives_saved,
            "comments_synced": comments_saved,
            "page": page.name
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Erreur synchronisation lives: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ==================== WEBHOOK ENDPOINTS ====================

@router.post("/webhook/subscribe")
async def subscribe_to_webhooks(
    request: WebhookSubscriptionRequest,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Souscrit aux webhooks Facebook pour une page"""
    try:
        page = db.query(FacebookPage).filter(
            FacebookPage.page_id == request.page_id,
            FacebookPage.seller_id == current_seller.id,
            FacebookPage.is_selected == True
        ).first()
        
        if not page:
            raise HTTPException(status_code=404, detail="Page non trouvée ou non sélectionnée")
        
        # Vérifier si déjà souscrit
        existing_sub = db.query(FacebookWebhookSubscription).filter(
            FacebookWebhookSubscription.page_id == page.page_id,
            FacebookWebhookSubscription.seller_id == current_seller.id
        ).first()
        
        if existing_sub and not request.force_resubscribe:
            return {
                "success": True,
                "message": "Déjà souscrit aux webhooks",
                "subscription_id": str(existing_sub.id)
            }
        
        # Souscrire aux webhooks via Graph API
        subscription_fields = [
            "feed",           # Posts, likes, comments
            "conversations",  # Messages
            "messages",       # Messages Messenger
            "live_videos",    # Lives
        ]
        
        result = await facebook_graph_service.subscribe_to_webhooks(
            page_id=page.page_id,
            access_token=page.page_access_token,
            fields=subscription_fields
        )
        
        if not result.get("success"):
            raise HTTPException(
                status_code=400,
                detail=f"Erreur Facebook: {result.get('error', 'Unknown')}"
            )
        
        # Enregistrer la subscription en base
        if existing_sub:
            subscription = existing_sub
            subscription.subscribed_fields = json.dumps(subscription_fields)
            subscription.is_active = True
            subscription.last_received = datetime.utcnow()
            subscription.updated_at = datetime.utcnow()
        else:
            subscription = FacebookWebhookSubscription(
                page_id=page.page_id,
                subscription_type="webhook",
                is_active=True,
                last_received=datetime.utcnow(),
                seller_id=current_seller.id,
                created_at=datetime.utcnow()
            )
            db.add(subscription)
        
        db.commit()
        
        return {
            "success": True,
            "message": "Webhooks souscrits avec succès",
            "subscription_id": str(subscription.id),
            "fields": subscription_fields
        }
            
    except Exception as e:
        logger.error(f"❌ Erreur subscription webhook: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/webhook")
async def facebook_webhook_challenge(
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_challenge: str = Query(..., alias="hub.challenge"),
    hub_verify_token: str = Query(..., alias="hub.verify_token"),
):
    """Validation du webhook Facebook"""
    if hub_mode == "subscribe" and hub_verify_token == settings.FACEBOOK_WEBHOOK_VERIFY_TOKEN:
        logger.info(f"✅ Webhook Facebook validé. Challenge={hub_challenge}")
        return int(hub_challenge)

    logger.error("❌ Token de vérification invalide")
    raise HTTPException(status_code=403, detail="Verification token mismatch")

@router.post("/webhook")
async def facebook_webhook_receive(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Reçoit et traite les événements webhook de Facebook"""
    try:
        # Lire le corps brut pour vérifier la signature
        raw_body = await request.body()
        body_json = json.loads(raw_body.decode('utf-8'))
        
        # Vérifier la signature X-Hub-Signature
        signature = request.headers.get("x-hub-signature")
        if signature and not facebook_webhook_service.verify_signature(raw_body, signature):
            logger.error("❌ Signature webhook invalide")
            raise HTTPException(status_code=403, detail="Invalid signature")
        
        # Journaliser l'événement brut
        webhook_log = FacebookWebhookLog(
            object_type=body_json.get("object", "unknown"),
            event_type="webhook_received",
            entry_id=body_json.get("entry", [{}])[0].get("id") if body_json.get("entry") else None,
            payload=body_json,
            signature=signature,
            created_at=datetime.utcnow()
        )
        db.add(webhook_log)
        db.commit()
        
        # Traiter dans une tâche de fond pour répondre rapidement à Facebook
        background_tasks.add_task(
            process_webhook_async,
            webhook_log.id,
            body_json,
            db
        )
        
        logger.info(f"📥 Webhook reçu: {body_json.get('object')}. Traitement en background.")
        return {"success": True}
        
    except Exception as e:
        logger.error(f"❌ Erreur webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ==================== COMMENTS MANAGEMENT ====================

@router.get("/comments")
async def get_comments(
    page_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Récupère les commentaires Facebook"""
    try:
        query = db.query(FacebookComment).filter(
            FacebookComment.seller_id == current_seller.id
        )
        
        if page_id:
            # Trouver la page correspondante
            page = db.query(FacebookPage).filter(
                FacebookPage.page_id == page_id,
                FacebookPage.seller_id == current_seller.id
            ).first()
            if page:
                query = query.filter(FacebookComment.page_id == str(page.id))
        
        if status:
            query = query.filter(FacebookComment.status == status)
        
        # Compter le total
        total = query.count()
        
        # Récupérer les commentaires
        comments = query.order_by(FacebookComment.created_at.desc()).offset(offset).limit(limit).all()
        
        # Formater la réponse
        comments_data = []
        for comment in comments:
            comments_data.append({
                "id": comment.id,
                "message": comment.message or "",
                "user_name": comment.user_name or "Inconnu",
                "post_id": comment.post_id,
                "status": comment.status or "new",
                "intent": comment.intent or "UNPROCESSABLE",
                "sentiment": comment.sentiment,
                "created_at": comment.created_at.isoformat() if comment.created_at else None,
                "detected_code_article": comment.detected_code_article,
                "detected_quantity": comment.detected_quantity or 0
            })
        
        return {
            "success": True,
            "count": len(comments),
            "total": total,
            "comments": comments_data
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur récupération commentaires: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ==================== DISCONNECT ENDPOINT ====================

@router.get("/disconnect")
async def disconnect_facebook(
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Déconnecte le vendeur de Facebook"""
    try:
        # 1. Trouver l'utilisateur Facebook du vendeur
        facebook_user = db.query(FacebookUser).filter(
            FacebookUser.seller_id == current_seller.id
        ).first()
        
        if not facebook_user:
            return {
                "success": True,
                "message": "Aucun compte Facebook connecté"
            }
        
        # 2. Trouver toutes les pages liées à cet utilisateur
        pages = db.query(FacebookPage).filter(
            FacebookPage.facebook_user_id == facebook_user.id
        ).all()
        
        # 3. Pour chaque page, supprimer d'abord les données enfants
        for page in pages:
            # Supprimer les commentaires liés à cette page (via post_id)
            # D'abord trouver tous les posts de cette page
            posts = db.query(FacebookPost).filter(
                FacebookPost.page_id == page.id
            ).all()
            
            for post in posts:
                # Supprimer les commentaires de ce post
                db.query(FacebookComment).filter(
                    FacebookComment.post_id == post.facebook_post_id
                ).delete()
                
                # Supprimer les logs NLP pour ces commentaires
                comment_ids = db.query(FacebookComment.id).filter(
                    FacebookComment.post_id == post.facebook_post_id
                ).all()
                
                if comment_ids:
                    db.query(NLPProcessingLog).filter(
                        NLPProcessingLog.comment_id.in_([c[0] for c in comment_ids])
                    ).delete()
            
            # Supprimer les posts de cette page
            db.query(FacebookPost).filter(
                FacebookPost.page_id == page.id
            ).delete()
            
            # Supprimer les lives videos de cette page
            db.query(FacebookLiveVideo).filter(
                FacebookLiveVideo.page_id == page.page_id
            ).delete()
            
            # CORRECTION ICI : Utiliser FacebookMessage au lieu de Message
            # Supprimer les messages Facebook liés à cette page
            db.query(FacebookMessage).filter(
                FacebookMessage.seller_id == page.seller_id
            ).delete()
            
            # Supprimer les messages Messenger
            db.query(MessengerMessage).filter(
                MessengerMessage.seller_id == page.seller_id
            ).delete()
            
            # Supprimer les logs webhook pour cette page
            db.query(FacebookWebhookLog).filter(
                FacebookWebhookLog.page_id == page.page_id
            ).delete()
        
        # 4. Maintenant supprimer les pages
        db.query(FacebookPage).filter(
            FacebookPage.facebook_user_id == facebook_user.id
        ).delete()
        
        # 5. Supprimer les subscriptions webhook
        db.query(FacebookWebhookSubscription).filter(
            FacebookWebhookSubscription.seller_id == current_seller.id
        ).delete()
        
        # 6. Supprimer les reply history
        db.query(FacebookReplyHistory).filter(
            FacebookReplyHistory.order_id.in_(
                db.query(Order.id).filter(Order.seller_id == current_seller.id).subquery()
            )
        ).delete()
        
        # 7. Supprimer les messages Messenger restants
        db.query(MessengerMessage).filter(
            MessengerMessage.seller_id == current_seller.id
        ).delete()
        
        # 8. Supprimer aussi les messages Facebook restants
        db.query(FacebookMessage).filter(
            FacebookMessage.seller_id == current_seller.id
        ).delete()
        
        # 9. Supprimer les logs webhook restants
        page_ids = [p.page_id for p in pages]
        if page_ids:
            db.query(FacebookWebhookLog).filter(
                FacebookWebhookLog.page_id.in_(page_ids)
            ).delete()
        
        # 10. Supprimer l'utilisateur Facebook
        db.delete(facebook_user)
        
        db.commit()
        
        return {
            "success": True,
            "message": "Compte Facebook déconnecté avec succès"
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Erreur déconnexion Facebook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ==================== SYNC COMMENTS ENDPOINT ====================

@router.post("/sync/comments/{post_id}")
async def sync_post_comments(
    post_id: str,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Synchronise les commentaires d'un post spécifique"""
    try:
        # Récupérer le post
        post = db.query(FacebookPost).filter(
            FacebookPost.facebook_post_id == post_id,
            FacebookPost.seller_id == current_seller.id
        ).first()
        
        if not post:
            raise HTTPException(status_code=404, detail="Post non trouvé")
        
        # Récupérer la page
        page = db.query(FacebookPage).filter(
            FacebookPage.id == post.page_id,
            FacebookPage.seller_id == current_seller.id
        ).first()
        
        if not page or not page.page_access_token:
            raise HTTPException(status_code=400, detail="Page ou token manquant")
        
        logger.info(f"🔄 Synchronisation commentaires pour post: {post_id}")
        
        # Récupérer les commentaires
        comments, _ = await facebook_graph_service.get_post_comments(
            post_id=post_id,
            access_token=page.page_access_token,
            limit=100
        )
        
        logger.info(f"📥 {len(comments)} commentaires récupérés")
        
        comments_saved = 0
        for comment_data in comments:
            comment_saved = await _save_comment_from_api(
                comment_data,
                current_seller.id,
                str(page.id),
                post_id,
                db
            )
            if comment_saved:
                comments_saved += 1
        
        db.commit()
        
        return {
            "success": True,
            "message": f"{comments_saved} commentaires synchronisés",
            "post_id": post_id,
            "comments_synced": comments_saved
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Erreur sync commentaires: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
# ==================== COMMENT PROCESSING ENDPOINTS ====================

# ============ FONCTION D'EXTRACTION QUANTITÉ ============
def extract_quantity_from_message(msg: str) -> Optional[int]:
    """Extrait la quantité totale du message en additionnant toutes les quantités trouvées"""
    
    total_quantity = 0
    found_positions = []
    
    # 1. Chercher les quantités associées aux codes produits (format: "2 APL-AP2")
    # Ce pattern capture spécifiquement le nombre juste avant un code produit
    product_pattern = r'\b(\d+)\s*(?:x\s*)?[A-Z]{2,4}-[A-Z0-9]{2,6}\b'
    product_matches = list(re.finditer(product_pattern, msg, re.IGNORECASE))
    
    for match in product_matches:
        quantity = int(match.group(1))
        total_quantity += quantity
        # Enregistrer la position pour éviter les doublons
        found_positions.append((match.start(), match.end()))
    
    # 2. Chercher les quantités explicites (quantité: 3, 2 pièces, etc.)
    explicit_patterns = [
        r'quantit[ée]\s*[:=]?\s*(\d+)',
        r'\b(\d+)\s+(?:pc|pi[èe]ce|unit[ée]|fois)\b',
        r'\b(\d+)x\s+[^\d]',  # "3x iPhone" (mais pas "3x4")
    ]
    
    for pattern in explicit_patterns:
        matches = list(re.finditer(pattern, msg, re.IGNORECASE))
        for match in matches:
            # Vérifier si cette position n'a pas déjà été comptée
            current_pos = (match.start(), match.end())
            if not any(start <= current_pos[0] < end for start, end in found_positions):
                quantity = int(match.group(1))
                total_quantity += quantity
                found_positions.append(current_pos)
    
    # 3. Si on a trouvé des quantités via les patterns, retourner la somme
    if total_quantity > 0:
        return total_quantity
    
    # 4. Fallback: chercher tous les nombres dans un contexte d'achat
    all_numbers = list(re.finditer(r'\b(\d+)\b', msg))
    if all_numbers and ("je veux" in msg.lower() or "je prends" in msg.lower() or "jp" in msg.lower()):
        purchase_quantities = []
        
        for match in all_numbers:
            num_str = match.group(1)
            num = int(num_str)
            
            # Filtrer: seulement les petites quantités (1-20)
            if 1 <= num <= 20:
                # Vérifier le contexte pour éviter les tailles, prix, etc.
                start_idx = max(0, match.start() - 10)
                end_idx = min(len(msg), match.end() + 10)
                context = msg[start_idx:end_idx].lower()
                
                # Exclure les contextes indésirables
                exclude_patterns = [
                    r'taille\s*\d', r'size\s*\d', r'\d+\s*[/-]\s*\d+',  # Tailles
                    r'\$\d', r'euro\s*\d', r'€\s*\d', r'\d+\s*€',  # Prix
                    r'\d+\s*cm', r'\d+\s*kg', r'\d+\s*g',  # Mesures
                ]
                
                is_excluded = False
                for exclude_pattern in exclude_patterns:
                    if re.search(exclude_pattern, context):
                        is_excluded = True
                        break
                
                # Inclure seulement si contexte d'achat
                include_keywords = ["apl-", "acc-", "vet-", "x", "pc", "pièce", "unité", "jp"]
                if not is_excluded and any(keyword in context for keyword in include_keywords):
                    purchase_quantities.append(num)
        
        if purchase_quantities:
            return sum(purchase_quantities)
    
    return None


@router.post("/comments/process")
async def process_facebook_comments(
    comment_ids: Optional[List[str]] = Query(None),
    page_id: Optional[str] = Query(None),
    auto_create_orders: bool = Query(False),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Traite les commentaires Facebook pour détecter les intentions d'achat
    """
    
    try:
        # Construire la requête
        query = db.query(FacebookComment).filter(
            FacebookComment.seller_id == current_seller.id,
            FacebookComment.status == 'new'
        )
        
        if comment_ids:
            query = query.filter(FacebookComment.id.in_(comment_ids))
        
        if page_id:
            page = db.query(FacebookPage).filter(
                FacebookPage.page_id == page_id,
                FacebookPage.seller_id == current_seller.id
            ).first()
            if page:
                query = query.filter(FacebookComment.page_id == str(page.id))
        
        comments = query.limit(50).all()
        
        if not comments:
            return {
                "success": True,
                "message": "Aucun commentaire à traiter",
                "processed": 0
            }
        
        processed = 0
        orders_created = 0
        
        for comment in comments:
            try:
                message = comment.message or ""
                message_lower = message.lower()
                
                # Détection CORRIGÉE des intentions
                intent = "UNPROCESSABLE"
                
                # 1. Détection d'achat (SIMPLIFIÉE)
                purchase_keywords = [
                    "je prends", "je veux", "commande", "achète", "commander",
                    "je prend", "je voudrais", "je désire", "donne moi", "donne-moi",
                    "je veux acheter", "je souhaite", "je souhaiterais", "je commande",
                    "je réserve", "je vais prendre", "je vais acheter",
                    "jp", "je prens", "je vx", "j'achète", "j'acheterais"
                ]
                
                # 2. "jp" = "je prends" (TRÈS IMPORTANT)
                if "jp" in message_lower:
                    # "jp" signifie toujours une intention d'achat
                    intent = "PURCHASE_INTENT"
                elif any(keyword in message_lower for keyword in purchase_keywords):
                    intent = "PURCHASE_INTENT"
                
                # 3. Détection de question
                question_keywords = ["?", "quel", "quelle", "quand", "comment", "combien", "où", "prix", "disponible", "est disponible"]
                if intent == "UNPROCESSABLE" and any(keyword in message_lower for keyword in question_keywords):
                    intent = "QUESTION"
                
                # 4. Codes produits
                product_codes = re.findall(r'\b[A-Z]{2,4}-[A-Z0-9]{2,6}\b', message)
                
                # 5. Autres intents
                if intent == "UNPROCESSABLE":
                    if "merci" in message_lower or "super" in message_lower or "bravo" in message_lower or "excellent" in message_lower:
                        intent = "POSITIVE_FEEDBACK"
                    elif "livraison" in message_lower or "livrer" in message_lower or "livraison rapide" in message_lower:
                        intent = "DELIVERY_QUESTION"
                    elif "disponible" in message_lower or "stock" in message_lower:
                        intent = "AVAILABILITY_QUESTION"
                    elif product_codes:
                        # Si produit détecté mais pas d'intention claire
                        intent = "PRODUCT_INQUIRY"
                
                # Mettre à jour le commentaire
                comment.status = 'processed'
                comment.intent = intent
                comment.updated_at = datetime.utcnow()
                
                # Détection des codes produits
                if product_codes:
                    comment.detected_code_article = ','.join(product_codes)
                
                # Extraire la quantité
                detected_quantity = extract_quantity_from_message(message)
                if detected_quantity:
                    comment.detected_quantity = detected_quantity
                elif product_codes and not comment.detected_quantity:
                    # Par défaut, 1 si produit détecté mais pas de quantité spécifiée
                    comment.detected_quantity = 1
                
                # CRÉATION AUTOMATIQUE DE COMMANDES (si activé)
                if auto_create_orders and intent == "PURCHASE_INTENT" and comment.detected_code_article:
                    try:
                        logger.info(f"🛒 Création auto commande pour commentaire {comment.id}")
                        
                        # Créer la commande automatiquement
                        order_result = await auto_create_order_from_facebook_comment(
                            comment=comment,
                            seller_id=current_seller.id,
                            db=db
                        )
                        
                        if order_result and order_result.get("success"):
                            orders_created += 1
                            comment.status = "order_created"
                            comment.intent = "ORDER_CREATED"
                            logger.info(f"✅ Commande créée: {order_result['order_number']}")
                        else:
                            comment.intent = "PURCHASE_INTENT"
                            comment.status = "needs_review"
                            logger.info(f"⚠️ Commande non créée, besoin de review")
                            
                    except Exception as order_error:
                        logger.error(f"❌ Erreur création commande: {order_error}")
                        comment.status = "error"
                
                db.add(comment)
                processed += 1
                
            except Exception as e:
                logger.error(f"Erreur traitement commentaire {comment.id}: {e}")
                comment.status = 'error'
                comment.intent = "ERROR"
                db.add(comment)
        
        db.commit()
        
        return {
            "success": True,
            "message": f"{processed} commentaires traités" + (f", {orders_created} commandes créées" if orders_created > 0 else ""),
            "processed": processed,
            "orders_created": orders_created,
            "intents_detected": True
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur traitement commentaires: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/comments/ready-for-orders")
async def get_comments_ready_for_orders(
    page_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Récupère les commentaires prêts à être convertis en commandes"""
    try:
        query = db.query(FacebookComment).filter(
            FacebookComment.seller_id == current_seller.id,
            FacebookComment.intent == "PURCHASE_INTENT",
            FacebookComment.detected_code_article.isnot(None),
            FacebookComment.status.in_(["new", "processed"])
        ).order_by(FacebookComment.created_at.desc())
        
        if page_id:
            page = db.query(FacebookPage).filter(
                FacebookPage.page_id == page_id,
                FacebookPage.seller_id == current_seller.id
            ).first()
            if page:
                query = query.filter(FacebookComment.page_id == str(page.id))
        
        comments = query.limit(limit).all()
        
        return {
            "success": True,
            "count": len(comments),
            "comments": [
                {
                    "id": c.id,
                    "message": c.message[:100] + "..." if c.message and len(c.message) > 100 else c.message or "",
                    "user_name": c.user_name,
                    "detected_code_article": c.detected_code_article,
                    "detected_quantity": c.detected_quantity,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "status": c.status,
                    "can_create_order": True
                }
                for c in comments
            ]
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur récupération commentaires prêts: {e}")
        raise HTTPException(status_code=500, detail=str(e))
# Ajoutez cette fonction dans facebook.py (après les imports)

from app.services.order_service import OrderService
from app.services.order_builder import OrderBuilderService

async def auto_create_order_from_facebook_comment(
    comment: FacebookComment,
    seller_id: str,
    db: Session
) -> Optional[Dict[str, Any]]:
    """
    Crée automatiquement une commande depuis un commentaire Facebook
    Version corrigée et simplifiée
    """
    try:
        logger.info(f"🛒 ========== DÉBUT CRÉATION COMMANDE ==========")
        logger.info(f"🛒 Commentaire ID: {comment.id}")
        logger.info(f"🛒 Message: {comment.message}")
        logger.info(f"🛒 Intent: {comment.intent}")
        logger.info(f"🛒 Status: {comment.status}")
        logger.info(f"🛒 Code article: {comment.detected_code_article}")
        logger.info(f"🛒 Quantité: {comment.detected_quantity}")
        logger.info(f"🛒 Utilisateur: {comment.user_name}")
        
        # 1. Vérifier si le commentaire a déjà une commande
        existing_order = db.query(Order).filter(
            Order.source_id == comment.id,
            Order.seller_id == seller_id
        ).first()
        
        if existing_order:
            logger.info(f"⚠️ Commande existe déjà: {existing_order.order_number}")
            return {
                "success": True,
                "order_id": str(existing_order.id),
                "order_number": existing_order.order_number,
                "message": "Commande existe déjà"
            }
        
        # 2. Vérifications de base
        if not comment.detected_code_article:
            logger.warning("⚠️ Pas de code article détecté - ABANDON")
            return None
        
        if comment.intent != "PURCHASE_INTENT":
            logger.warning(f"⚠️ Intent incorrect: {comment.intent} - ABANDON")
            return None
        
        # 3. Préparer les items de commande
        from app.services.order_service import OrderService
        from app.schemas.order import OrderCreate, OrderItemCreate
        from app.models import Product
        
        order_service = OrderService(db)
        product_codes = [code.strip() for code in comment.detected_code_article.split(',')]
        items = []
        
        logger.info(f"📦 Préparation {len(product_codes)} produits...")
        
        for product_code in product_codes:
            # Chercher le produit dans la base
            product = db.query(Product).filter(Product.code == product_code).first()
            
            if product:
                logger.info(f"   ✅ Produit trouvé: {product.name} ({product_code}) - {float(product.price) if product.price else 10000.0} MGA")
                items.append(OrderItemCreate(
                    product_id=product.id,
                    product_name=product.name,
                    product_code=product_code,
                    quantity=comment.detected_quantity or 1,
                    unit_price=float(product.price) if product.price else 10000.0
                ))
            else:
                logger.warning(f"   ⚠️ Produit {product_code} non trouvé - utilisation valeurs par défaut")
                items.append(OrderItemCreate(
                    product_id=None,  # NULL autorisé maintenant
                    product_name=f"Produit {product_code}",
                    product_code=product_code,
                    quantity=comment.detected_quantity or 1,
                    unit_price=10000.0  # Prix par défaut
                ))
        
        if not items:
            logger.error("❌ Aucun item valide créé - ABANDON")
            return None
        
        # 4. Créer la commande
        logger.info(f"📝 Création commande avec {len(items)} items...")
        
        order_data = OrderCreate(
            customer_name=comment.user_name or "Client Facebook",
            customer_phone="À confirmer",
            shipping_address="À confirmer",
            needs_delivery=True,
            items=items,
            source="facebook_comment",
            source_id=comment.id
        )
        
        order = order_service.create_order(seller_id, order_data)
        
        if order:
            # Mettre à jour le commentaire
            comment.status = "order_created"
            comment.intent = "ORDER_CREATED"
            db.add(comment)
            db.commit()
            
            logger.info(f"✅ COMMANDE CRÉÉE: {order.order_number}")
            logger.info(f"   Montant total: {order.total_amount} MGA")
            logger.info(f"   Client: {order.customer_name}")
            logger.info(f"   Items: {len(items)}")
            
            # Envoyer une notification (optionnel)
            try:
                await send_facebook_reply(
                    comment_id=comment.id,
                    page_id=comment.page_id,
                    message=f"✅ Commande confirmée !\n\nRéférence: {order.order_number}\nMontant: {order.total_amount} MGA\nNous vous contacterons bientôt."
                )
            except Exception as e:
                logger.warning(f"⚠️ Erreur notification: {e}")
            
            return {
                "success": True,
                "order_id": str(order.id),
                "order_number": order.order_number,
                "total_amount": float(order.total_amount),
                "items_count": len(items),
                "customer_name": order.customer_name
            }
        else:
            logger.error("❌ Échec création commande par OrderService")
            return None
        
    except Exception as e:
        logger.error(f"❌ ERREUR CRITIQUE création commande: {e}", exc_info=True)
        db.rollback()
        return None

@router.post("/comments/{comment_id}/create-order")
async def create_order_from_comment_manual(
    comment_id: str,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Crée manuellement une commande depuis un commentaire Facebook"""
    try:
        logger.info(f"🎯 DÉBUT création manuelle commande pour: {comment_id}")
        
        # 1. Récupérer le commentaire
        comment = db.query(FacebookComment).filter(
            FacebookComment.id == comment_id,
            FacebookComment.seller_id == current_seller.id
        ).first()
        
        if not comment:
            logger.error(f"❌ Commentaire {comment_id} non trouvé")
            raise HTTPException(status_code=404, detail="Commentaire non trouvé")
        
        logger.info(f"📝 Commentaire trouvé: {comment.user_name} - {comment.detected_code_article}")
        
        # 2. Vérifier si une commande existe déjà
        existing_order = db.query(Order).filter(
            Order.source_id == comment.id,
            Order.seller_id == current_seller.id
        ).first()
        
        if existing_order:
            logger.info(f"⚠️ Commande existe déjà: {existing_order.order_number}")
            return {
                "success": True,
                "message": "Commande existe déjà",
                "order_number": existing_order.order_number,
                "order_id": str(existing_order.id),
                "total_amount": float(existing_order.total_amount)
            }
        
        # 3. Vérifier les prérequis
        if not comment.detected_code_article:
            logger.error("❌ Pas de code produit détecté")
            raise HTTPException(
                status_code=400, 
                detail="Pas de code produit détecté dans le commentaire"
            )
        
        # 4. Utiliser OrderService directement
        from app.services.order_service import OrderService
        from app.schemas.order import OrderCreate, OrderItemCreate
        from app.models import Product
        
        order_service = OrderService(db)
        
        # 5. Préparer les items
        product_codes = [code.strip() for code in comment.detected_code_article.split(',')]
        items = []
        
        logger.info(f"📦 Préparation {len(product_codes)} produit(s)...")
        
        for product_code in product_codes:
            product = db.query(Product).filter(Product.code_article == product_code).first()
            
            if product:
                logger.info(f"   ✅ Produit trouvé: {product.name} ({product_code})")
                items.append(OrderItemCreate(
                    product_id=product.id,
                    product_name=product.name,
                    product_code=product_code,
                    quantity=comment.detected_quantity or 1,
                    unit_price=float(product.price) if product.price else 10000.0
                ))
            else:
                logger.warning(f"   ⚠️ Produit {product_code} non trouvé - valeurs par défaut")
                items.append(OrderItemCreate(
                    product_id=None,
                    product_name=f"Produit {product_code}",
                    product_code=product_code,
                    quantity=comment.detected_quantity or 1,
                    unit_price=10000.0
                ))
        
        if not items:
            logger.error("❌ Aucun item valide créé")
            raise HTTPException(
                status_code=400,
                detail="Impossible de créer des items de commande"
            )
        
        # 6. Créer la commande
        logger.info(f"📝 Création commande avec {len(items)} item(s)...")
        
        order_data = OrderCreate(
            customer_name=comment.user_name or "Client Facebook",
            customer_phone="À confirmer",
            shipping_address="À confirmer",
            needs_delivery=True,
            items=items,
            source="facebook_comment",
            source_id=comment.id
        )
        
        order = order_service.create_order(current_seller.id, order_data)
        
        if order:
            # Mettre à jour le commentaire
            comment.status = "processed"  # Utilisez un statut existant
            comment.intent = "ORDER_CREATED"
            db.add(comment)
            db.commit()
            
            logger.info(f"✅ COMMANDE CRÉÉE: {order.order_number}")
            logger.info(f"   Montant: {order.total_amount} MGA")
            logger.info(f"   Client: {order.customer_name}")
            
            return {
                "success": True,
                "message": "Commande créée avec succès",
                "order_id": str(order.id),
                "order_number": order.order_number,
                "total_amount": float(order.total_amount),
                "customer_name": order.customer_name,
                "items_count": len(items)
            }
        else:
            logger.error("❌ Échec création par OrderService")
            raise HTTPException(
                status_code=500,
                detail="Erreur lors de la création de la commande"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erreur création manuelle: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur interne: {str(e)}")


async def send_facebook_reply(comment_id: str, page_id: str, message: str):
    """Envoie une réponse à un commentaire Facebook"""
    try:
        # Récupérer le token de la page
        db = SessionLocal()
        page = db.query(FacebookPage).filter(FacebookPage.page_id == page_id).first()
        
        if page and page.page_access_token:
            import httpx
            async with httpx.AsyncClient() as client:
                url = f"https://graph.facebook.com/v18.0/{comment_id}/comments"
                params = {
                    "access_token": page.page_access_token,
                    "message": message
                }
                
                response = await client.post(url, params=params)
                if response.status_code == 200:
                    logger.info(f"✅ Réponse envoyée à {comment_id}")
                else:
                    logger.warning(f"⚠️ Erreur réponse Facebook: {response.text}")
        
        db.close()
    except Exception as e:
        logger.warning(f"⚠️ Erreur envoi réponse: {e}")

# ============ ROUTE POUR RÉINITIALISER LES COMMENTAIRES ============

@router.post("/comments/reset-for-test")
async def reset_comments_for_test(
    comment_ids: Optional[List[str]] = Query(None),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Réinitialise des commentaires pour tester la création de commandes"""
    try:
        query = db.query(FacebookComment).filter(
            FacebookComment.seller_id == current_seller.id,
            FacebookComment.status == 'processed'
        )
        
        if comment_ids:
            query = query.filter(FacebookComment.id.in_(comment_ids))
        else:
            # Prendre les 10 premiers avec intention d'achat
            query = query.filter(FacebookComment.intent == 'PURCHASE_INTENT')
            query = query.order_by(FacebookComment.created_at.desc()).limit(10)
        
        comments = query.all()
        
        for comment in comments:
            comment.status = 'new'
            comment.intent = 'UNPROCESSABLE'
            comment.updated_at = datetime.utcnow()
            db.add(comment)
        
        db.commit()
        
        return {
            "success": True,
            "message": f"{len(comments)} commentaires réinitialisés",
            "comment_ids": [c.id for c in comments]
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur réinitialisation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/comments/pending")
async def get_pending_comments(
    page_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Récupère les commentaires en attente de traitement
    """
    try:
        query = db.query(FacebookComment).filter(
            FacebookComment.seller_id == current_seller.id,
            FacebookComment.status == 'new'
        )
        
        if page_id:
            page = db.query(FacebookPage).filter(
                FacebookPage.page_id == page_id,
                FacebookPage.seller_id == current_seller.id
            ).first()
            if page:
                query = query.filter(FacebookComment.page_id == str(page.id))
        
        total = query.count()
        comments = query.order_by(FacebookComment.created_at.desc()).limit(limit).all()
        
        return {
            "success": True,
            "count": len(comments),
            "total": total,
            "comments": [
                {
                    "id": c.id,
                    "message": c.message[:100] + "..." if c.message and len(c.message) > 100 else c.message or "",
                    "user_name": c.user_name,
                    "post_id": c.post_id,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "has_product_codes": bool(c.detected_code_article)
                }
                for c in comments
            ]
        }
        
    except Exception as e:
        logger.error(f"Erreur récupération commentaires pending: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== TEST ENDPOINTS ====================

@router.get("/comments/test-quantity")
async def test_quantity_extraction(
    message: str = Query(..., description="Message à tester"),
    current_seller = Depends(get_current_seller)
):
    """
    Teste l'extraction de quantité d'un message
    """
    
    def extract_quantity_from_message(msg: str) -> Optional[int]:
        """Même fonction que dans /comments/process"""
        total_quantity = 0
        found_positions = []
        
        # 1. Chercher les quantités associées aux codes produits
        product_pattern = r'\b(\d+)\s*(?:x\s*)?[A-Z]{2,4}-[A-Z0-9]{2,6}\b'
        product_matches = list(re.finditer(product_pattern, msg, re.IGNORECASE))
        
        for match in product_matches:
            quantity = int(match.group(1))
            total_quantity += quantity
            found_positions.append((match.start(), match.end()))
        
        # 2. Chercher les quantités explicites
        explicit_patterns = [
            r'quantit[ée]\s*[:=]?\s*(\d+)',
            r'\b(\d+)\s+(?:pc|pi[èe]ce|unit[ée]|fois)\b',
            r'\b(\d+)x\s+[^\d]',
        ]
        
        for pattern in explicit_patterns:
            matches = list(re.finditer(pattern, msg, re.IGNORECASE))
            for match in matches:
                current_pos = (match.start(), match.end())
                if not any(start <= current_pos[0] < end for start, end in found_positions):
                    quantity = int(match.group(1))
                    total_quantity += quantity
                    found_positions.append(current_pos)
        
        # 3. Si on a trouvé des quantités
        if total_quantity > 0:
            return total_quantity
        
        # 4. Fallback
        all_numbers = list(re.finditer(r'\b(\d+)\b', msg))
        if all_numbers and ("je veux" in msg.lower() or "je prends" in msg.lower() or "jp" in msg.lower()):
            purchase_quantities = []
            
            for match in all_numbers:
                num_str = match.group(1)
                num = int(num_str)
                
                if 1 <= num <= 20:
                    start_idx = max(0, match.start() - 10)
                    end_idx = min(len(msg), match.end() + 10)
                    context = msg[start_idx:end_idx].lower()
                    
                    exclude_patterns = [
                        r'taille\s*\d', r'size\s*\d', r'\d+\s*[/-]\s*\d+',
                        r'\$\d', r'euro\s*\d', r'€\s*\d', r'\d+\s*€',
                        r'\d+\s*cm', r'\d+\s*kg', r'\d+\s*g',
                    ]
                    
                    is_excluded = False
                    for exclude_pattern in exclude_patterns:
                        if re.search(exclude_pattern, context):
                            is_excluded = True
                            break
                    
                    include_keywords = ["apl-", "acc-", "vet-", "x", "pc", "pièce", "unité", "jp"]
                    if not is_excluded and any(keyword in context for keyword in include_keywords):
                        purchase_quantities.append(num)
            
            if purchase_quantities:
                return sum(purchase_quantities)
        
        return None
    
    # Analyse du message
    product_codes = re.findall(r'\b[A-Z]{2,4}-[A-Z0-9]{2,6}\b', message)
    numbers_found = re.findall(r'\b(\d+)\b', message)
    
    # Extraire la quantité avec la nouvelle fonction
    detected_quantity = extract_quantity_from_message(message)
    
    return {
        "success": True,
        "message": message,
        "detected_quantity": detected_quantity,
        "analysis": {
            "has_numbers": len(numbers_found) > 0,
            "numbers_found": numbers_found,
            "product_codes_found": product_codes
        }
    }

@router.get("/comments/test-intent")
async def test_intent_detection(
    text: str = Query(..., description="Texte à analyser"),
    current_seller = Depends(get_current_seller)
):
    """Teste la détection d'intention sur un texte"""
    
    # Fonction d'extraction de quantité (simplifiée)
    def extract_quantity_from_message(msg: str) -> Optional[int]:
        total_quantity = 0
        
        # Pattern pour codes produits : "2 APL-AP2" ou "2xAPL-AP2"
        product_pattern = r'\b(\d+)\s*(?:x\s*)?[A-Z]{2,4}-[A-Z0-9]{2,6}\b'
        product_matches = list(re.finditer(product_pattern, msg, re.IGNORECASE))
        
        for match in product_matches:
            quantity = int(match.group(1))
            total_quantity += quantity
        
        return total_quantity if total_quantity > 0 else None
    
    # Détection de codes produits
    product_codes = re.findall(r'\b[A-Z]{2,4}-[A-Z0-9]{2,6}\b', text)
    
    # Détection d'intention basée sur mots-clés
    text_lower = text.lower()
    intent = "UNPROCESSABLE"
    confidence = 0.0
    
    # Mots-clés d'achat (incluant "jp")
    purchase_keywords = ['je veux', 'je prends', 'commande', 'achète', 'jp', 'je prens', 'j\'achète']
    question_keywords = ['?', 'quel', 'quelle', 'quand', 'comment', 'combien', 'où', 'prix', 'disponible']
    
    if any(keyword in text_lower for keyword in purchase_keywords):
        if "jp" in text_lower:
            if product_codes or any(word in text_lower for word in ["svp", "stp"]):
                intent = "PURCHASE_INTENT"
                confidence = 0.9
            else:
                intent = "PRODUCT_INQUIRY"
                confidence = 0.7
        else:
            intent = "PURCHASE_INTENT"
            confidence = 0.8
    elif any(keyword in text_lower for keyword in question_keywords):
        intent = "QUESTION"
        confidence = 0.8
    elif "merci" in text_lower or "super" in text_lower or "bravo" in text_lower:
        intent = "POSITIVE_FEEDBACK"
        confidence = 0.9
    elif "livraison" in text_lower:
        intent = "DELIVERY_QUESTION"
        confidence = 0.7
    elif "disponible" in text_lower or "stock" in text_lower:
        intent = "AVAILABILITY_QUESTION"
        confidence = 0.7
    
    # Si produit détecté mais intention inconnue
    if product_codes and intent == "UNPROCESSABLE":
        intent = "PRODUCT_INQUIRY"
        confidence = 0.6
    
    quantity = extract_quantity_from_message(text)
    
    return {
        "success": True,
        "text": text,
        "intent": intent,
        "confidence": confidence,
        "product_codes": product_codes,
        "quantity_detected": quantity,
        "purchase_keywords_found": [k for k in purchase_keywords if k in text_lower],
        "is_jp_message": "jp" in text_lower
    }

@router.get("/api-test")
async def test_facebook_api(
    page_id: Optional[str] = Query(None),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Teste directement l'API Facebook"""
    try:
        # Récupérer la page
        page = db.query(FacebookPage).filter(
            FacebookPage.page_id == page_id,
            FacebookPage.seller_id == current_seller.id
        ).first() if page_id else db.query(FacebookPage).filter(
            FacebookPage.seller_id == current_seller.id,
            FacebookPage.is_selected == True
        ).first()
        
        if not page:
            return {"error": "Page non trouvée"}
        
        # Test simple de l'API
        import httpx
        
        # Test 1: Récupérer les infos de la page
        async with httpx.AsyncClient() as client:
            url = f"https://graph.facebook.com/v18.0/{page.page_id}"
            params = {
                "access_token": page.page_access_token,
                "fields": "id,name,fan_count"
            }
            
            response = await client.get(url, params=params)
            page_info = response.json()
            
            if "error" in page_info:
                return {
                    "success": False,
                    "error": page_info["error"],
                    "message": "Erreur API Facebook"
                }
        
        # Test 2: Récupérer quelques posts
        posts, paging = await facebook_graph_service.get_page_posts(
            page_id=page.page_id,
            access_token=page.page_access_token,
            limit=3
        )
        
        # Test 3: Pour chaque post, tester les commentaires
        posts_with_comments = []
        for post in posts:
            post_id = post.get("id")
            comments_count = post.get("comments", {}).get("summary", {}).get("total_count", 0)
            
            comments_info = {
                "post_id": post_id,
                "comments_count_from_post": comments_count
            }
            
            if comments_count > 0:
                comments, _ = await facebook_graph_service.get_post_comments(
                    post_id=post_id,
                    access_token=page.page_access_token,
                    limit=5
                )
                comments_info["comments_retrieved"] = len(comments)
                comments_info["sample_comments"] = [
                    {
                        "id": c.get("id"),
                        "user": c.get("from", {}).get("name", "Unknown"),
                        "message_preview": c.get("message", "")[:50]
                    }
                    for c in comments[:2]
                ]
            
            posts_with_comments.append(comments_info)
        
        return {
            "success": True,
            "page_info": {
                "id": page_info.get("id"),
                "name": page_info.get("name"),
                "fan_count": page_info.get("fan_count")
            },
            "posts_test": {
                "total_posts_retrieved": len(posts),
                "posts_sample": [
                    {
                        "id": p.get("id"),
                        "has_message": "message" in p,
                        "has_story": "story" in p,
                        "likes_count": p.get("likes", {}).get("summary", {}).get("total_count", 0),
                        "comments_count": p.get("comments", {}).get("summary", {}).get("total_count", 0)
                    }
                    for p in posts[:3]
                ],
                "comments_test": posts_with_comments
            },
            "api_status": "OK"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "Erreur lors du test API"
        }

@router.get("/webhook/health")
async def webhook_health(
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Vérifie l'état des webhooks"""
    try:
        # Récupérer les pages sélectionnées du vendeur
        pages = db.query(FacebookPage).filter(
            FacebookPage.seller_id == current_seller.id,
            FacebookPage.is_selected == True
        ).all()
        
        subscriptions = []
        for page in pages:
            sub = db.query(FacebookWebhookSubscription).filter(
                FacebookWebhookSubscription.page_id == page.page_id,
                FacebookWebhookSubscription.is_active == True
            ).first()
            
            if sub:
                subscriptions.append({
                    "page_id": page.page_id,
                    "page_name": page.name,
                    "subscription_id": sub.subscription_type,
                    "last_received": sub.last_received.isoformat() if sub.last_received else None
                })
        
        # Derniers webhooks reçus
        recent_webhooks = db.query(FacebookWebhookLog).order_by(
            FacebookWebhookLog.created_at.desc()
        ).limit(10).all()
        
        return {
            "success": True,
            "timestamp": datetime.utcnow().isoformat(),
            "subscriptions": {
                "count": len(subscriptions),
                "active": subscriptions
            },
            "recent_webhooks": [
                {
                    "id": str(wh.id),
                    "object": wh.object_type,
                    "received_at": wh.created_at.isoformat() if wh.created_at else None,
                    "processed": wh.processed
                }
                for wh in recent_webhooks
            ],
            "webhook_url": f"{settings.APP_URL}/api/v1/facebook/webhook" if settings.APP_URL else "Not configured",
            "nlp_service_available": nlp_service is not None
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur webhook health: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))