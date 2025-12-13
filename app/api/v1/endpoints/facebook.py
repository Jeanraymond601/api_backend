# app/api/v1/endpoints/facebook.py
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status, BackgroundTasks
from fastapi.responses import RedirectResponse, JSONResponse, StreamingResponse
import httpx
from sqlalchemy.orm import Session, joinedload
from typing import Dict, List, Optional, Any, AsyncGenerator
import logging
import json
import hashlib
import hmac
from uuid import UUID
import asyncio
import csv
from io import StringIO

from app.db import get_db
from app.services.facebook_auth import facebook_auth_service
from app.services.facebook_webhook import FacebookWebhookService
from app.services.facebook_graph_api import FacebookGraphAPIService
from app.schemas.facebook import (
    FacebookConnectRequest,
    FacebookConnectResponse,
    FacebookAuthResponse,
    FacebookPageResponse,
    FacebookWebhookChallenge,
    FacebookWebhookEvent,
    SelectPageRequest,
    SelectPageResponse,
    SyncRequest,
    FacebookCommentResponse as CommentResponse,
    MessageResponse,
    FacebookLiveVideoResponse as LiveVideoResponse,
    FacebookPostResponse as PostResponse,
    WebhookSubscriptionRequest,
)
from app.models.facebook import (
    FacebookComment, FacebookLiveVideo, FacebookMessage, 
    FacebookPost, FacebookUser, FacebookPage, FacebookWebhookLog,
    FacebookMessageTemplate, FacebookWebhookSubscription
)
from app.core.security import get_current_seller, get_current_user
from app.core.config import settings
from app.services.nlp_service import NLPService

router = APIRouter()
logger = logging.getLogger(__name__)

# ⭐ Services
facebook_webhook_service = FacebookWebhookService()
facebook_graph_service = FacebookGraphAPIService()
nlp_service = NLPService()

# ==================== AUTHENTICATION & CONNECTION ====================

@router.get("/login", response_model=FacebookConnectResponse)
async def facebook_login(
    request: Request,
    fb_request: FacebookConnectRequest = Depends(),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Génère l'URL OAuth pour la connexion Facebook
    """
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
        
        # Générer l'URL OAuth avec les permissions étendues
        state = fb_request.state or str(current_seller.id)
        permissions = [
            "pages_show_list",
            "pages_read_engagement",  # Pour les posts, commentaires
            "pages_manage_posts",     # Pour publier
            "pages_messaging",        # Pour les messages
            "pages_read_user_content", # Pour lire le contenu utilisateur
            "pages_manage_metadata",  # Pour gérer les métadonnées
            "business_management"     # Pour la gestion business
        ]
        
        auth_url = facebook_auth_service.get_oauth_url(state)
        
        return FacebookConnectResponse(
            success=True,
            auth_url=auth_url,
            state=state
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la génération de l'URL OAuth: {e}")
        raise HTTPException(
            status_code=500,
            detail="Erreur lors de la connexion à Facebook"
        )

@router.get("/callback", response_model=FacebookAuthResponse)
async def facebook_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db)
):
    """
    Callback OAuth Facebook
    """
    try:
        # Échanger le code contre un token d'accès
        token_data = await facebook_auth_service.exchange_code_for_token(code)
        
        # Récupérer les infos utilisateur Facebook
        user_info = await facebook_auth_service.get_user_info(token_data["access_token"])
        
        # Récupérer les pages de l'utilisateur
        pages = await facebook_auth_service.get_user_pages(token_data["access_token"])
        
        # Sauvegarder en base
        facebook_user = FacebookUser(
            facebook_id=user_info["id"],
            name=user_info.get("name"),
            email=user_info.get("email"),
            access_token=token_data["access_token"],
            token_expires_at=datetime.fromtimestamp(token_data.get("expires_in", 0) + datetime.now().timestamp()),
            seller_id=UUID(state),  # state contient le seller_id
            is_active=True
        )
        db.add(facebook_user)
        db.flush()
        
        # Sauvegarder les pages
        for page in pages:
            fb_page = FacebookPage(
                page_id=page["id"],
                name=page.get("name"),
                category=page.get("category"),
                page_access_token=page.get("access_token"),
                token_expires_at=datetime.fromtimestamp(page.get("expires_in", 0) + datetime.now().timestamp()),
                facebook_user_id=facebook_user.id,
                seller_id=UUID(state),
                is_selected=False
            )
            db.add(fb_page)
        
        db.commit()
        
        return FacebookAuthResponse(
            success=True,
            message="Connexion Facebook réussie",
            user=user_info,
            pages=pages
        )
        
    except Exception as e:
        logger.error(f"Erreur callback Facebook: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la connexion: {str(e)}"
        )

# ==================== PAGES MANAGEMENT ====================

@router.get("/pages", response_model=List[FacebookPageResponse])
async def get_facebook_pages(
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Récupère toutes les pages Facebook du vendeur
    """
    try:
        pages = db.query(FacebookPage).filter(
            FacebookPage.seller_id == current_seller.id
        ).all()
        
        return [
            FacebookPageResponse(
                id=str(page.id),
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
        logger.error(f"Erreur récupération pages: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/pages/select", response_model=SelectPageResponse)
async def select_facebook_page(
    request: SelectPageRequest,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Sélectionne une page Facebook comme page active
    """
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
        
        page.is_selected = True
        page.updated_at = datetime.utcnow()
        db.commit()
        
        return SelectPageResponse(
            success=True,
            message=f"Page {page.name} sélectionnée avec succès",
            page=FacebookPageResponse(
                id=str(page.id),
                page_id=page.page_id,
                name=page.name,
                category=page.category,
                fan_count=page.fan_count,
                is_selected=True,
                cover_photo_url=page.cover_photo_url,
                profile_pic_url=page.profile_pic_url
            )
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur sélection page: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== WEBHOOK MANAGEMENT ====================

@router.post("/webhook/subscribe")
async def subscribe_to_webhooks(
    request: WebhookSubscriptionRequest,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Souscrit aux webhooks Facebook pour une page
    """
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
            FacebookWebhookSubscription.page_id == page.page_id
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
            "messaging_postbacks",  # Actions messages
            "messaging_optins",     # Opt-ins
            "messaging_referrals",  # Références
            "message_deliveries",   # Livraison messages
            "message_reads",        # Messages lus
            "messaging_handovers",  # Transferts
            "messaging_policy_enforcement",  # Politique
            "live_videos",    # Lives
            "video_publishing",  # Publications vidéos
            "ratings",        # Évaluations
            "mention",        # Mentions
            "standby"         # Mode veille
        ]
        
        # Créer l'URL du webhook
        webhook_url = f"{settings.APP_URL}/api/v1/facebook/webhook"
        
        async with httpx.AsyncClient() as client:
            # Souscrire aux webhooks
            response = await client.post(
                f"https://graph.facebook.com/v18.0/{page.page_id}/subscribed_apps",
                params={
                    "subscribed_fields": ",".join(subscription_fields),
                    "access_token": page.page_access_token
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Erreur subscription: {response.text}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Erreur Facebook: {response.json().get('error', {}).get('message', 'Unknown')}"
                )
            
            result = response.json()
            
            # Enregistrer la subscription en base
            if existing_sub:
                subscription = existing_sub
                subscription.subscribed_fields = json.dumps(subscription_fields)
                subscription.webhook_url = webhook_url
                subscription.is_active = True
                subscription.last_sync = datetime.utcnow()
                subscription.updated_at = datetime.utcnow()
            else:
                subscription = FacebookWebhookSubscription(
                    page_id=page.page_id,
                    subscription_id=result.get("id"),
                    subscribed_fields=json.dumps(subscription_fields),
                    webhook_url=webhook_url,
                    is_active=True,
                    last_sync=datetime.utcnow(),
                    seller_id=current_seller.id
                )
                db.add(subscription)
            
            db.commit()
            
            return {
                "success": True,
                "message": "Webhooks souscrits avec succès",
                "subscription_id": str(subscription.id),
                "fields": subscription_fields,
                "webhook_url": webhook_url
            }
            
    except Exception as e:
        logger.error(f"Erreur subscription webhook: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/webhook")
async def facebook_webhook_challenge(
    challenge: FacebookWebhookChallenge = Depends()
):
    """
    Validation du webhook Facebook (GET)
    """
    if challenge.hub_mode == "subscribe" and challenge.hub_verify_token == settings.FACEBOOK_WEBHOOK_VERIFY_TOKEN:
        logger.info(f"✅ Webhook Facebook validé avec succès. Challenge: {challenge.hub_challenge}")
        return int(challenge.hub_challenge)
    
    raise HTTPException(status_code=403, detail="Verification token mismatch")

@router.post("/webhook")
async def facebook_webhook_receive(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Reçoit et traite les événements webhook de Facebook
    """
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

async def process_webhook_async(webhook_log_id: UUID, body_json: dict, db: Session):
    """Traite le webhook de manière asynchrone"""
    try:
        # Récupérer le log
        webhook_log = db.query(FacebookWebhookLog).filter(FacebookWebhookLog.id == webhook_log_id).first()
        if not webhook_log:
            logger.error(f"Log webhook {webhook_log_id} non trouvé")
            return
        
        object_type = body_json.get("object")
        entries = body_json.get("entry", [])
        
        for entry in entries:
            # Identifier la page
            page_id = entry.get("id")
            page = db.query(FacebookPage).filter(FacebookPage.page_id == page_id).first()
            
            if not page:
                logger.warning(f"Page {page_id} non trouvée en base")
                continue
            
            # Traiter les changements
            changes = entry.get("changes", [])
            for change in changes:
                await process_webhook_change(change, page, db)
            
            # Traiter les messages Messenger
            messaging = entry.get("messaging", [])
            for message_event in messaging:
                await process_messaging_event(message_event, page, db)
            
            # Traiter les standbys (mode veille)
            standby = entry.get("standby", [])
            for standby_event in standby:
                await process_standby_event(standby_event, page, db)
        
        # Marquer comme traité
        webhook_log.processed = True
        webhook_log.processed_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"✅ Webhook {webhook_log_id} traité avec succès")
        
    except Exception as e:
        logger.error(f"❌ Erreur traitement webhook async: {e}", exc_info=True)
        db.rollback()

async def process_webhook_change(change: dict, page: FacebookPage, db: Session):
    """Traite un changement de webhook"""
    field = change.get("field")
    value = change.get("value")
    
    logger.info(f"🔄 Changement détecté: {field} pour page {page.page_id}")
    
    if field == "feed":
        await process_feed_change(value, page, db)
    elif field == "conversations":
        await process_conversations_change(value, page, db)
    elif field == "live_videos":
        await process_live_videos_change(value, page, db)
    elif field == "ratings":
        await process_ratings_change(value, page, db)
    elif field == "mention":
        await process_mention_change(value, page, db)

async def process_feed_change(value: dict, page: FacebookPage, db: Session):
    """Traite les changements de feed (posts, commentaires)"""
    item = value.get("item")
    verb = value.get("verb")
    post_id = value.get("post_id")
    comment_id = value.get("comment_id")
    parent_id = value.get("parent_id")  # Pour les réponses aux commentaires
    
    if item == "post" and verb == "add":
        # Nouveau post
        await fetch_and_save_post(post_id, page, db)
        
    elif item == "comment" and verb == "add":
        # Nouveau commentaire
        await fetch_and_save_comment(comment_id, page, db)
        
        # Analyser l'intention avec NLP
        comment = db.query(FacebookComment).filter(
            FacebookComment.id == comment_id
        ).first()
        
        if comment:
            # Analyser l'intention
            intent = nlp_service.analyze_comment_intent(comment.message)
            comment.intent = intent.get("intent")
            comment.sentiment = intent.get("sentiment")
            comment.entities = json.dumps(intent.get("entities", []))
            
            # Marquer comme prioritaire si nécessaire
            if intent.get("priority", False):
                comment.priority = "high"
            
            db.commit()
            
            # Notifier en temps réel si configuré
            await notify_real_time_comment(comment, page)
    
    elif item == "comment" and verb == "edit":
        # Commentaire modifié
        await update_comment(comment_id, page, db)
    
    elif item == "comment" and verb == "remove":
        # Commentaire supprimé
        await mark_comment_deleted(comment_id, db)

async def process_messaging_event(event: dict, page: FacebookPage, db: Session):
    """Traite les événements Messenger"""
    sender = event.get("sender", {}).get("id")
    recipient = event.get("recipient", {}).get("id")
    timestamp = event.get("timestamp")
    
    # Message texte
    if "message" in event:
        message_data = event["message"]
        message_id = message_data.get("mid")
        text = message_data.get("text", "")
        
        # Sauvegarder le message
        message = FacebookMessage(
            message_id=message_id,
            sender_id=sender,
            recipient_id=recipient,
            page_id=page.page_id,
            message_type="text",
            content=text,
            direction="incoming",
            status="received",
            metadata=json.dumps({
                "quick_reply": message_data.get("quick_reply"),
                "attachments": message_data.get("attachments"),
                "is_echo": message_data.get("is_echo", False)
            })
        )
        db.add(message)
        db.commit()
        
        # Analyser avec NLP
        intent = nlp_service.analyze_message_intent(text)
        message.intent = intent.get("intent")
        message.sentiment = intent.get("sentiment")
        db.commit()
        
        # Réponse automatique si configurée
        await handle_auto_reply(message, page, db)
    
    # Postback (boutons)
    elif "postback" in event:
        postback = event["postback"]
        payload = postback.get("payload")
        
        message = FacebookMessage(
            message_id=f"postback_{timestamp}",
            sender_id=sender,
            recipient_id=recipient,
            page_id=page.page_id,
            message_type="postback",
            content=payload,
            direction="incoming",
            status="received",
            metadata=json.dumps(postback)
        )
        db.add(message)
        db.commit()
        
        await handle_postback(payload, sender, page, db)
    
    # Livraison message
    elif "delivery" in event:
        mids = event["delivery"].get("mids", [])
        for mid in mids:
            message = db.query(FacebookMessage).filter(
                FacebookMessage.message_id == mid
            ).first()
            if message:
                message.status = "delivered"
    
    # Lecture message
    elif "read" in event:
        watermark = event["read"].get("watermark")
        # Marquer les messages comme lus
        messages = db.query(FacebookMessage).filter(
            FacebookMessage.sender_id == sender,
            FacebookMessage.page_id == page.page_id,
            FacebookMessage.created_at <= datetime.fromtimestamp(watermark/1000)
        ).all()
        
        for msg in messages:
            msg.status = "read"
        db.commit()

async def process_live_videos_change(value: dict, page: FacebookPage, db: Session):
    """Traite les changements de lives vidéos"""
    video_id = value.get("video_id")
    status = value.get("status")
    
    if not video_id:
        return
    
    # Récupérer les infos du live
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://graph.facebook.com/v18.0/{video_id}",
            params={
                "fields": "id,title,description,status,creation_time,"
                         "scheduled_start_time,live_views,end_time,"
                         "permalink_url,from",
                "access_token": page.page_access_token
            }
        )
        
        if response.status_code == 200:
            video_data = response.json()
            
            # Chercher ou créer le live
            live = db.query(FacebookLiveVideo).filter(
                FacebookLiveVideo.facebook_video_id == video_id
            ).first()
            
            if live:
                # Mettre à jour
                live.status = video_data.get("status")
                live.live_views = video_data.get("live_views")
                if status == "live":
                    live.actual_start_time = datetime.utcnow()
                elif status == "archived":
                    live.end_time = datetime.utcnow()
                    live.duration = (datetime.utcnow() - live.actual_start_time).total_seconds() if live.actual_start_time else 0
            else:
                # Créer
                live = FacebookLiveVideo(
                    facebook_video_id=video_id,
                    page_id=page.page_id,
                    title=video_data.get("title"),
                    description=video_data.get("description"),
                    status=video_data.get("status"),
                    scheduled_start_time=datetime.fromisoformat(
                        video_data.get("scheduled_start_time").replace("Z", "+00:00")
                    ) if video_data.get("scheduled_start_time") else None,
                    actual_start_time=datetime.fromisoformat(
                        video_data.get("creation_time").replace("Z", "+00:00")
                    ) if video_data.get("creation_time") else None,
                    seller_id=page.seller_id
                )
                db.add(live)
            
            db.commit()
            logger.info(f"🎥 Live {video_id} mis à jour: {status}")

async def fetch_and_save_post(post_id: str, page: FacebookPage, db: Session):
    """Récupère et sauvegarde un post Facebook"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://graph.facebook.com/v18.0/{post_id}",
                params={
                    "fields": "id,message,created_time,updated_time,full_picture,"
                             "permalink_url,likes.summary(true),comments.summary(true),"
                             "shares,attachments,type,is_hidden,is_published,"
                             "is_expired,is_instagram_eligible,is_popular",
                    "access_token": page.page_access_token
                }
            )
            
            if response.status_code == 200:
                post_data = response.json()
                
                # Vérifier si existe déjà
                existing = db.query(FacebookPost).filter(
                    FacebookPost.post_id == post_id
                ).first()
                
                if not existing:
                    post = FacebookPost(
                        post_id=post_id,
                        message=post_data.get("message"),
                        type=post_data.get("type"),
                        picture_url=post_data.get("full_picture"),
                        link=post_data.get("attachments", {}).get("data", [{}])[0].get("url") 
                             if post_data.get("attachments") else None,
                        likes_count=post_data.get("likes", {}).get("summary", {}).get("total_count", 0),
                        comments_count=post_data.get("comments", {}).get("summary", {}).get("total_count", 0),
                        shares_count=post_data.get("shares", {}).get("count", 0) 
                                if post_data.get("shares") else 0,
                        page_id=page.id,
                        seller_id=page.seller_id,
                        facebook_created_time=datetime.fromisoformat(
                            post_data.get("created_time").replace("Z", "+00:00")
                        ),
                        is_live_commerce=False,
                        metadata=json.dumps({
                            "is_hidden": post_data.get("is_hidden"),
                            "is_published": post_data.get("is_published"),
                            "is_popular": post_data.get("is_popular"),
                            "permalink": post_data.get("permalink_url")
                        })
                    )
                    db.add(post)
                    db.commit()
                    
                    # Analyser si c'est du live commerce
                    if post.message:
                        analysis = nlp_service.analyze_post_for_live_commerce(post.message)
                        if analysis.get("is_live_commerce"):
                            post.is_live_commerce = True
                            post.live_commerce_score = analysis.get("score")
                            db.commit()
                    
                    logger.info(f"📝 Nouveau post sauvegardé: {post_id}")
                    
    except Exception as e:
        logger.error(f"❌ Erreur fetch post {post_id}: {e}")

async def fetch_and_save_comment(comment_id: str, page: FacebookPage, db: Session):
    """Récupère et sauvegarde un commentaire"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://graph.facebook.com/v18.0/{comment_id}",
                params={
                    "fields": "id,message,created_time,from{id,name},"
                             "like_count,comment_count,parent,attachment",
                    "access_token": page.page_access_token
                }
            )
            
            if response.status_code == 200:
                comment_data = response.json()
                
                # Vérifier si existe déjà
                existing = db.query(FacebookComment).filter(
                    FacebookComment.id == comment_id
                ).first()
                
                if not existing:
                    comment = FacebookComment(
                        id=comment_id,
                        message=comment_data.get("message"),
                        user_id=comment_data.get("from", {}).get("id"),
                        user_name=comment_data.get("from", {}).get("name"),
                        post_id=comment_data.get("parent", {}).get("id") 
                               if comment_data.get("parent") else None,
                        seller_id=page.seller_id,
                        page_id=page.id,
                        status="new",
                        facebook_created_time=datetime.fromisoformat(
                            comment_data.get("created_time").replace("Z", "+00:00")
                        ),
                        metadata=json.dumps({
                            "like_count": comment_data.get("like_count"),
                            "comment_count": comment_data.get("comment_count"),
                            "attachment": comment_data.get("attachment")
                        })
                    )
                    db.add(comment)
                    db.commit()
                    logger.info(f"💬 Nouveau commentaire sauvegardé: {comment_id}")
                    
    except Exception as e:
        logger.error(f"❌ Erreur fetch comment {comment_id}: {e}")

# ==================== REAL-TIME NOTIFICATIONS ====================

@router.get("/webhook/stream")
async def webhook_stream(
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Stream SSE (Server-Sent Events) pour les notifications en temps réel
    """
    async def event_generator():
        """Générateur d'événements SSE"""
        last_id = None
        
        while True:
            # Récupérer les nouveaux événements
            query = db.query(FacebookWebhookLog).filter(
                FacebookWebhookLog.processed == True
            ).order_by(FacebookWebhookLog.processed_at.desc()).limit(10)
            
            if last_id:
                query = query.filter(FacebookWebhookLog.id > last_id)
            
            events = query.all()
            
            for event in events:
                last_id = event.id
                
                # Formater l'événement pour le SSE
                event_data = {
                    "id": str(event.id),
                    "type": event.event_type,
                    "object": event.object_type,
                    "timestamp": event.processed_at.isoformat() if event.processed_at else None,
                    "data": {
                        "entry_id": event.entry_id,
                        "seller_id": str(current_seller.id)
                    }
                }
                
                yield f"data: {json.dumps(event_data)}\n\n"
            
            await asyncio.sleep(2)  # Poll toutes les 2 secondes
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Pour Nginx
        }
    )

@router.get("/notifications/recent")
async def get_recent_notifications(
    limit: int = Query(20, ge=1, le=100),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Récupère les notifications récentes
    """
    try:
        # Récupérer les pages du vendeur
        pages = db.query(FacebookPage).filter(
            FacebookPage.seller_id == current_seller.id
        ).all()
        
        page_ids = [page.id for page in pages]
        page_fb_ids = [page.page_id for page in pages]
        
        # Commentaires récents
        recent_comments = db.query(FacebookComment).filter(
            FacebookComment.page_id.in_(page_ids),
            FacebookComment.status == "new"
        ).order_by(FacebookComment.created_at.desc()).limit(limit).all()
        
        # Messages récents
        recent_messages = db.query(FacebookMessage).filter(
            FacebookMessage.page_id.in_(page_fb_ids),
            FacebookMessage.direction == "incoming",
            FacebookMessage.status == "received"
        ).order_by(FacebookMessage.created_at.desc()).limit(limit).all()
        
        # Lives actifs
        active_lives = db.query(FacebookLiveVideo).filter(
            FacebookLiveVideo.page_id.in_(page_fb_ids),
            FacebookLiveVideo.status == "live"
        ).order_by(FacebookLiveVideo.actual_start_time.desc()).all()
        
        return {
            "success": True,
            "timestamp": datetime.utcnow().isoformat(),
            "counts": {
                "new_comments": len(recent_comments),
                "new_messages": len(recent_messages),
                "active_lives": len(active_lives)
            },
            "comments": [
                {
                    "id": comment.id,
                    "message": comment.message,
                    "user_name": comment.user_name,
                    "post_id": comment.post_id,
                    "status": comment.status,
                    "intent": comment.intent,
                    "sentiment": comment.sentiment,
                    "created_at": comment.created_at.isoformat() if comment.created_at else None
                }
                for comment in recent_comments
            ],
            "messages": [
                {
                    "message_id": msg.message_id,
                    "content": msg.content,
                    "sender_id": msg.sender_id,
                    "page_id": msg.page_id,
                    "intent": msg.intent,
                    "sentiment": msg.sentiment,
                    "created_at": msg.created_at.isoformat() if msg.created_at else None
                }
                for msg in recent_messages
            ],
            "lives": [
                {
                    "video_id": live.facebook_video_id,
                    "title": live.title,
                    "status": live.status,
                    "live_views": live.live_views,
                    "actual_start_time": live.actual_start_time.isoformat() if live.actual_start_time else None
                }
                for live in active_lives
            ]
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur récupération notifications: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== MESSAGE MANAGEMENT ====================

@router.post("/messages/{message_id}/reply")
async def reply_to_message(
    message_id: str,
    reply_data: dict,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Répond à un message Messenger
    """
    try:
        # Récupérer le message original
        message = db.query(FacebookMessage).filter(
            FacebookMessage.message_id == message_id,
            FacebookMessage.page_id.in_(
                db.query(FacebookPage.page_id).filter(
                    FacebookPage.seller_id == current_seller.id
                )
            )
        ).first()
        
        if not message:
            raise HTTPException(status_code=404, detail="Message non trouvé")
        
        # Récupérer la page
        page = db.query(FacebookPage).filter(
            FacebookPage.page_id == message.page_id
        ).first()
        
        if not page:
            raise HTTPException(status_code=404, detail="Page non trouvée")
        
        # Vérifier le texte de réponse
        reply_text = reply_data.get("text", "").strip()
        if not reply_text:
            raise HTTPException(status_code=400, detail="Le texte de réponse ne peut pas être vide")
        
        # Envoyer la réponse via Graph API
        response = await facebook_graph_service.send_message(
            page_id=page.page_id,
            recipient_id=message.sender_id,
            message_text=reply_text,
            access_token=page.page_access_token
        )
        
        if response.get("message_id"):
            # Sauvegarder la réponse envoyée
            reply_message = FacebookMessage(
                message_id=response["message_id"],
                sender_id=page.page_id,
                recipient_id=message.sender_id,
                page_id=page.page_id,
                message_type="text",
                content=reply_text,
                direction="outgoing",
                status="sent",
                parent_message_id=message_id
            )
            db.add(reply_message)
            
            # Marquer le message original comme répondu
            message.status = "replied"
            message.replied_at = datetime.utcnow()
            
            db.commit()
            
            return {
                "success": True,
                "message_id": response["message_id"],
                "recipient_id": message.sender_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Erreur Facebook: {response.get('error', 'Unknown')}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erreur reply message: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

async def handle_auto_reply(message: FacebookMessage, page: FacebookPage, db: Session):
    """Gère les réponses automatiques"""
    # Vérifier si l'auto-réponse est activée pour cette page
    if not page.auto_reply_enabled:
        return
    
    # Analyser l'intention pour une réponse appropriée
    intent = message.intent
    
    # Chercher un template de réponse
    template = db.query(FacebookMessageTemplate).filter(
        FacebookMessageTemplate.intent == intent,
        FacebookMessageTemplate.page_id == page.id,
        FacebookMessageTemplate.is_active == True
    ).first()
    
    if template:
        # Envoyer la réponse automatique
        response = await facebook_graph_service.send_message(
            page_id=page.page_id,
            recipient_id=message.sender_id,
            message_text=template.response_text,
            access_token=page.page_access_token
        )
        
        if response.get("message_id"):
            # Marquer comme répondu automatiquement
            message.status = "auto_replied"
            message.auto_reply_template_id = template.id
            db.commit()

# ==================== LIVE COMMERCE MANAGEMENT ====================

@router.get("/live/{live_id}/analytics")
async def get_live_analytics(
    live_id: str,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Récupère les analytics d'un live
    """
    try:
        live = db.query(FacebookLiveVideo).filter(
            FacebookLiveVideo.facebook_video_id == live_id,
            FacebookLiveVideo.seller_id == current_seller.id
        ).first()
        
        if not live:
            raise HTTPException(status_code=404, detail="Live non trouvé")
        
        # Récupérer les commentaires du live
        comments = db.query(FacebookComment).filter(
            FacebookComment.post_id == live_id,
            FacebookComment.seller_id == current_seller.id
        ).all()
        
        # Analyser les commentaires
        comment_analysis = {
            "total": len(comments),
            "by_intent": {},
            "by_sentiment": {},
            "top_keywords": []
        }
        
        for comment in comments:
            # Compter par intention
            intent = comment.intent or "unknown"
            comment_analysis["by_intent"][intent] = comment_analysis["by_intent"].get(intent, 0) + 1
            
            # Compter par sentiment
            sentiment = comment.sentiment or "neutral"
            comment_analysis["by_sentiment"][sentiment] = comment_analysis["by_sentiment"].get(sentiment, 0) + 1
        
        # Récupérer les metrics du live depuis Facebook
        facebook_metrics = []
        page = db.query(FacebookPage).filter(
            FacebookPage.page_id == live.page_id
        ).first()
        
        if page and page.page_access_token:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://graph.facebook.com/v18.0/{live_id}/video_insights",
                    params={
                        "metric": "total_video_views,total_video_complete_views,"
                                 "total_video_retention_graph,"
                                 "total_video_avg_time_watched,"
                                 "total_video_impressions,"
                                 "total_video_engagement",
                        "access_token": page.page_access_token
                    }
                )
                
                if response.status_code == 200:
                    facebook_metrics = response.json().get("data", [])
        
        return {
            "success": True,
            "live_id": live_id,
            "live_title": live.title,
            "status": live.status,
            "duration": live.duration,
            "start_time": live.actual_start_time.isoformat() if live.actual_start_time else None,
            "end_time": live.end_time.isoformat() if live.end_time else None,
            "analytics": {
                "comments": comment_analysis,
                "facebook_metrics": facebook_metrics,
                "engagement_rate": (len(comments) / max(live.live_views or 1, 1)) * 100 if live.live_views else 0
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erreur analytics live: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== BULK OPERATIONS ====================

@router.post("/comments/bulk-process")
async def bulk_process_comments(
    comment_ids: List[str],
    action: str = Query(..., pattern="^(mark_read|reply_all|export|categorize)$"),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Traitement en masse des commentaires
    """
    try:
        # Récupérer les commentaires
        comments = db.query(FacebookComment).filter(
            FacebookComment.id.in_(comment_ids),
            FacebookComment.seller_id == current_seller.id
        ).all()
        
        if not comments:
            raise HTTPException(status_code=404, detail="Aucun commentaire trouvé")
        
        results = []
        
        if action == "mark_read":
            for comment in comments:
                comment.status = "processed"
                results.append({"id": comment.id, "status": "processed"})
            
            db.commit()
            
        elif action == "reply_all":
            # Récupérer la page (tous les commentaires doivent être de la même page)
            page_id = comments[0].page_id if comments else None
            page = db.query(FacebookPage).filter(FacebookPage.id == page_id).first()
            
            if page and page.page_access_token:
                # Template de réponse
                reply_text = "Merci pour votre commentaire ! Nous reviendrons vers vous rapidement."
                
                for comment in comments:
                    try:
                        # Envoyer la réponse via Graph API
                        response = await facebook_graph_service.send_comment_reply(
                            comment_id=comment.id,
                            message_text=reply_text,
                            access_token=page.page_access_token
                        )
                        
                        if response.get("id"):
                            comment.status = "replied"
                            comment.replied_at = datetime.utcnow()
                            results.append({"id": comment.id, "reply_id": response["id"]})
                        else:
                            results.append({"id": comment.id, "error": "Erreur Facebook"})
                    except Exception as e:
                        results.append({"id": comment.id, "error": str(e)})
                
                db.commit()
        
        elif action == "categorize":
            for comment in comments:
                if comment.message:
                    # Analyser avec NLP
                    analysis = nlp_service.analyze_comment_intent(comment.message)
                    comment.intent = analysis.get("intent")
                    comment.sentiment = analysis.get("sentiment")
                    results.append({"id": comment.id, "intent": comment.intent, "sentiment": comment.sentiment})
            
            db.commit()
        
        return {
            "success": True,
            "action": action,
            "processed": len(results),
            "results": results
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur bulk process: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ==================== EXPORT ====================

@router.get("/export/comments")
async def export_comments(
    format: str = Query("json", pattern="^(json|csv)$"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Exporte les commentaires
    """
    try:
        query = db.query(FacebookComment).filter(
            FacebookComment.seller_id == current_seller.id
        )
        
        if start_date:
            query = query.filter(FacebookComment.created_at >= start_date)
        if end_date:
            query = query.filter(FacebookComment.created_at <= end_date)
        
        comments = query.order_by(FacebookComment.created_at.desc()).all()
        
        if format == "json":
            return {
                "success": True,
                "format": "json",
                "count": len(comments),
                "data": [
                    {
                        "id": comment.id,
                        "message": comment.message,
                        "user_name": comment.user_name,
                        "post_id": comment.post_id,
                        "status": comment.status,
                        "intent": comment.intent,
                        "sentiment": comment.sentiment,
                        "created_at": comment.created_at.isoformat() if comment.created_at else None,
                        "facebook_created_time": comment.facebook_created_time.isoformat() if comment.facebook_created_time else None
                    }
                    for comment in comments
                ]
            }
        elif format == "csv":
            # Générer CSV
            output = StringIO()
            writer = csv.writer(output, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            
            # En-têtes
            writer.writerow([
                "ID", "Message", "User", "Post ID", "Status",
                "Intent", "Sentiment", "Created At", "Facebook Created Time"
            ])
            
            # Données
            for comment in comments:
                writer.writerow([
                    comment.id,
                    comment.message or "",
                    comment.user_name or "",
                    comment.post_id or "",
                    comment.status or "",
                    comment.intent or "",
                    comment.sentiment or "",
                    comment.created_at.isoformat() if comment.created_at else "",
                    comment.facebook_created_time.isoformat() if comment.facebook_created_time else ""
                ])
            
            output.seek(0)
            
            return StreamingResponse(
                iter([output.getvalue()]),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename=comments_export_{datetime.utcnow().date()}.csv"
                }
            )
        
    except Exception as e:
        logger.error(f"❌ Erreur export comments: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== HEALTH & MONITORING ====================

@router.get("/webhook/health")
async def webhook_health(
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Vérifie l'état des webhooks
    """
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
                    "subscription_id": sub.subscription_id,
                    "last_sync": sub.last_sync.isoformat() if sub.last_sync else None,
                    "fields": json.loads(sub.subscribed_fields) if sub.subscribed_fields else []
                })
        
        # Derniers webhooks reçus - CORRECTION ICI: utiliser created_at au lieu de received_at
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
                    "received_at": wh.created_at.isoformat() if wh.created_at else None,  # CORRECTION: created_at
                    "processed": wh.processed
                }
                for wh in recent_webhooks
            ],
            "webhook_url": f"{settings.APP_URL}/api/v1/facebook/webhook" if settings.APP_URL else "Not configured"
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur webhook health: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ==================== ADDITIONAL ENDPOINTS ====================

@router.get("/comments")
async def get_comments(
    page_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Récupère les commentaires avec filtres
    """
    try:
        query = db.query(FacebookComment).filter(
            FacebookComment.seller_id == current_seller.id
        )
        
        if page_id:
            # Trouver l'ID interne de la page
            page = db.query(FacebookPage).filter(
                FacebookPage.page_id == page_id,
                FacebookPage.seller_id == current_seller.id
            ).first()
            if page:
                query = query.filter(FacebookComment.page_id == page.id)
        
        if status:
            query = query.filter(FacebookComment.status == status)
        
        comments = query.order_by(FacebookComment.created_at.desc()).offset(offset).limit(limit).all()
        
        return {
            "success": True,
            "count": len(comments),
            "total": query.count(),
            "comments": [
                {
                    "id": comment.id,
                    "message": comment.message,
                    "user_name": comment.user_name,
                    "post_id": comment.post_id,
                    "status": comment.status,
                    "intent": comment.intent,
                    "sentiment": comment.sentiment,
                    "created_at": comment.created_at.isoformat() if comment.created_at else None
                }
                for comment in comments
            ]
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur récupération commentaires: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/disconnect")
async def disconnect_facebook(
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Déconnecte le vendeur de Facebook
    """
    try:
        # Supprimer toutes les données Facebook du vendeur
        facebook_user = db.query(FacebookUser).filter(
            FacebookUser.seller_id == current_seller.id
        ).first()
        
        if facebook_user:
            # Supprimer les pages
            db.query(FacebookPage).filter(
                FacebookPage.facebook_user_id == facebook_user.id
            ).delete()
            
            # Supprimer les subscriptions
            db.query(FacebookWebhookSubscription).filter(
                FacebookWebhookSubscription.seller_id == current_seller.id
            ).delete()
            
            # Supprimer l'utilisateur Facebook
            db.delete(facebook_user)
            
            db.commit()
            
            return {
                "success": True,
                "message": "Compte Facebook déconnecté avec succès"
            }
        else:
            return {
                "success": True,
                "message": "Aucun compte Facebook connecté"
            }
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Erreur déconnexion Facebook: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== SYNC ENDPOINTS ====================

@router.post("/sync")
async def sync_facebook_data(
    sync_request: SyncRequest,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Synchronise les données Facebook
    """
    try:
        page = db.query(FacebookPage).filter(
            FacebookPage.page_id == sync_request.page_id,
            FacebookPage.seller_id == current_seller.id
        ).first()
        
        if not page:
            raise HTTPException(status_code=404, detail="Page non trouvée")
        
        results = {}
        
        if sync_request.sync_posts:
            # Synchroniser les posts
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://graph.facebook.com/v18.0/{page.page_id}/posts",
                    params={
                        "fields": "id,message,created_time,updated_time,full_picture,permalink_url,likes.summary(true),comments.summary(true),shares,type",
                        "access_token": page.page_access_token,
                        "limit": 100
                    }
                )
                
                if response.status_code == 200:
                    posts = response.json().get("data", [])
                    results["posts"] = len(posts)
        
        return {
            "success": True,
            "message": "Synchronisation lancée",
            "results": results
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur synchronisation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== UTILITY FUNCTIONS ====================

async def notify_real_time_comment(comment: FacebookComment, page: FacebookPage):
    """Notifie en temps réel un nouveau commentaire"""
    notification_data = {
        "type": "new_comment",
        "comment_id": comment.id,
        "message": comment.message[:100] if comment.message else "",
        "user": comment.user_name,
        "page": page.name,
        "timestamp": datetime.utcnow().isoformat(),
        "intent": comment.intent,
        "sentiment": comment.sentiment,
        "priority": comment.priority
    }
    
    logger.info(f"📢 Notification commentaire: {comment.id}")
    # Ici, vous pouvez intégrer avec WebSockets, SSE, etc.

async def handle_postback(payload: str, sender_id: str, page: FacebookPage, db: Session):
    """Gère les postbacks Messenger"""
    if payload == "GET_STARTED":
        # Message de bienvenue
        welcome_message = "Bienvenue sur notre page ! Comment puis-je vous aider ?"
        
        await facebook_graph_service.send_message(
            page_id=page.page_id,
            recipient_id=sender_id,
            message_text=welcome_message,
            access_token=page.page_access_token
        )
    
    # Sauvegarder l'interaction
    interaction = FacebookMessage(
        message_id=f"postback_{int(datetime.utcnow().timestamp())}",
        sender_id=sender_id,
        recipient_id=page.page_id,
        page_id=page.page_id,
        message_type="postback",
        content=payload,
        direction="incoming",
        status="processed",
        metadata=json.dumps({"handler": "postback"})
    )
    db.add(interaction)
    db.commit()

# Helper functions
async def process_conversations_change(value: dict, page: FacebookPage, db: Session):
    """Traite les changements de conversations"""
    logger.info(f"🔄 Conversation change: {value}")

async def process_ratings_change(value: dict, page: FacebookPage, db: Session):
    """Traite les changements de ratings"""
    logger.info(f"⭐ Rating change: {value}")

async def process_mention_change(value: dict, page: FacebookPage, db: Session):
    """Traite les mentions"""
    logger.info(f"@ Mention change: {value}")

async def process_standby_event(event: dict, page: FacebookPage, db: Session):
    """Traite les événements standby"""
    logger.info(f"⏳ Standby event: {event}")

async def update_comment(comment_id: str, page: FacebookPage, db: Session):
    """Met à jour un commentaire"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://graph.facebook.com/v18.0/{comment_id}",
                params={
                    "fields": "id,message,from{id,name},like_count",
                    "access_token": page.page_access_token
                }
            )
            
            if response.status_code == 200:
                comment_data = response.json()
                comment = db.query(FacebookComment).filter(FacebookComment.id == comment_id).first()
                if comment:
                    comment.message = comment_data.get("message")
                    comment.updated_at = datetime.utcnow()
                    db.commit()
    except Exception as e:
        logger.error(f"❌ Erreur update comment {comment_id}: {e}")

async def mark_comment_deleted(comment_id: str, db: Session):
    """Marque un commentaire comme supprimé"""
    comment = db.query(FacebookComment).filter(FacebookComment.id == comment_id).first()
    if comment:
        comment.status = "deleted"
        comment.updated_at = datetime.utcnow()
        db.commit()